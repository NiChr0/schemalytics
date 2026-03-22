#!/usr/bin/env python3
"""
Parse Spider dataset CREATE TABLE statements into extracted JSON format.

Run from repo root:
    python finetune/scripts/extract_spider.py
"""

import json
import re
from pathlib import Path
from huggingface_hub import hf_hub_download
import pandas as pd

OUTPUT_DIR = Path("finetune/extracted_spider")
OUTPUT_DIR.mkdir(exist_ok=True)


def parse_create_table(sql: str) -> dict | None:
    """Parse a single CREATE TABLE statement into our schema dict format."""
    # Extract table name
    name_match = re.search(r'CREATE TABLE\s+(?:IF NOT EXISTS\s+)?["`]?(\w+)["`]?\s*\(', sql, re.IGNORECASE)
    if not name_match:
        return None
    table_name = name_match.group(1)

    columns = []
    primary_key = []
    foreign_keys = []

    # Strip outer parens content
    inner_match = re.search(r'\((.+)\)', sql, re.DOTALL)
    if not inner_match:
        return None
    inner = inner_match.group(1)

    # Split by comma but respect nested parens
    parts = []
    depth = 0
    current = ""
    for ch in inner:
        if ch == '(':
            depth += 1
            current += ch
        elif ch == ')':
            depth -= 1
            current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip())
            current = ""
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    for part in parts:
        part = part.strip()
        if not part:
            continue

        upper = part.upper()

        # PRIMARY KEY constraint
        if upper.startswith('PRIMARY KEY'):
            pk_match = re.findall(r'["`]?(\w+)["`]?', part[len('PRIMARY KEY'):])
            primary_key.extend(pk_match)
            continue

        # FOREIGN KEY constraint
        if upper.startswith('FOREIGN KEY'):
            fk_col = re.search(r'FOREIGN KEY\s*\(["`]?(\w+)["`]?\)', part, re.IGNORECASE)
            ref_table = re.search(r'REFERENCES\s+["`]?(\w+)["`]?\s*\(["`]?(\w+)["`]?\)', part, re.IGNORECASE)
            if fk_col and ref_table:
                foreign_keys.append({
                    "column": fk_col.group(1),
                    "references_table": ref_table.group(1),
                    "references_column": ref_table.group(2),
                })
            continue

        # UNIQUE / INDEX / CHECK constraints - skip
        if upper.startswith(('UNIQUE', 'INDEX', 'CHECK', 'CONSTRAINT')):
            continue

        # Column definition
        col_match = re.match(r'["`]?(\w+)["`]?\s+(\S+)', part)
        if col_match:
            col_name = col_match.group(1)
            data_type = col_match.group(2).upper().rstrip(',')
            nullable = 'NOT NULL' not in upper
            columns.append({
                "name": col_name,
                "data_type": data_type,
                "nullable": nullable,
                "description": None,
            })

    return {
        "name": table_name,
        "schema_name": "public",
        "columns": columns,
        "primary_key": primary_key,
        "foreign_keys": foreign_keys,
        "description": None,
    }


def main():
    print("Downloading spider_sql_schema parquet...")
    path = hf_hub_download(
        repo_id='KaifengGGG/spider_sql_schema',
        filename='data/train-00000-of-00001.parquet',
        repo_type='dataset'
    )
    df = pd.read_parquet(path)

    # One entry per unique db_id
    db_schemas = {}
    for _, row in df.iterrows():
        db_id = row['db_id']
        if db_id not in db_schemas:
            db_schemas[db_id] = row['schema']

    print(f"Found {len(db_schemas)} unique databases")

    written = 0
    skipped = 0
    for db_id, schema_sqls in db_schemas.items():
        tables = []
        for sql in schema_sqls:
            table = parse_create_table(sql)
            if table and table['columns']:
                tables.append(table)

        if not tables:
            skipped += 1
            continue

        out = {"tables": tables}
        out_path = OUTPUT_DIR / f"{db_id}.json"
        out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
        written += 1

    print(f"Written: {written} schemas to {OUTPUT_DIR}/")
    print(f"Skipped: {skipped} (no parseable tables)")


if __name__ == "__main__":
    main()
