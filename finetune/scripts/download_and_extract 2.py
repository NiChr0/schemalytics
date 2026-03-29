#!/usr/bin/env python3
"""
Download raw SQL schema files from GitHub and parse them into the
extracted JSON format used by label_silver.py.

Output: finetune/extracted_new/<db_id>.json

Run from repo root:
    python finetune/scripts/download_and_extract.py
"""

import json
import re
import sys
import time
from pathlib import Path

import requests
import sqlparse
from sqlparse.sql import Parenthesis, Statement
from sqlparse.tokens import Keyword, DDL, Punctuation, Name, Whitespace

# ---------------------------------------------------------------------------
# Sources
# ---------------------------------------------------------------------------

SOURCES = [
    # (db_id, raw_url)
    # Round 1 — confirmed working
    ("airline",             "https://raw.githubusercontent.com/prameshstha/airline-database/master/create.sql"),
    ("library_mgmt",        "https://raw.githubusercontent.com/virajmavani/library-management-system/master/create-library-data.sql"),
    ("library_hardik",      "https://raw.githubusercontent.com/hardiktrivedi0612/DBMS-library-management-system/master/Table%20Creation.sql"),

    # Round 2 — high-confidence sources
    # MySQL employees DB (canonical HR schema, datacharmer/test_db)
    ("employees",           "https://raw.githubusercontent.com/datacharmer/test_db/master/employees.sql"),
    # postgres_air airline DB (used in PostgreSQL book by Hettie D.)
    ("postgres_air",        "https://raw.githubusercontent.com/hettie-d/postgres_air/main/postgres_air/data/create_tables.sql"),
    # Hospital management system
    ("hospital_mgmt",       "https://raw.githubusercontent.com/ssanidhya0407/Hospital-Management-System/master/HospitalManagementDB.sql"),
    # Car rental / fleet
    ("car_rental",          "https://raw.githubusercontent.com/tejaskolhe27/Car-Rental-System/master/car_rental.sql"),
    # E-learning / LMS
    ("lms",                 "https://raw.githubusercontent.com/mrkrabs/learning-management-system/master/lms.sql"),
    # Banking system
    ("banking_system",      "https://raw.githubusercontent.com/Learning-Is-Vital-In-Development/banking-system/main/schema.sql"),
    # Inventory management
    ("inventory",           "https://raw.githubusercontent.com/techwithtim/Inventory-Management-System/master/schema.sql"),
    # Hotel management
    ("hotel_mgmt",          "https://raw.githubusercontent.com/RimpleMittal/Hotel-Management-Database/master/hotelmanagement.sql"),
    # Telecom billing
    ("telecom",             "https://raw.githubusercontent.com/alves-gabriel/telecom-database/master/schema.sql"),
    # Project management / issue tracker (Redmine-inspired)
    ("project_mgmt",        "https://raw.githubusercontent.com/brianloss/project-management-db/master/schema.sql"),
    # Clinical / pharmacy
    ("pharmacy",            "https://raw.githubusercontent.com/siddharth1702/Pharmacy-Management-System/master/pharmacy.sql"),
]

OUTPUT_DIR = Path("finetune/extracted_new")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# SQL parser
# ---------------------------------------------------------------------------

_TYPE_MAP = {
    "int": "INTEGER", "integer": "INTEGER", "bigint": "BIGINT",
    "smallint": "SMALLINT", "tinyint": "TINYINT",
    "float": "FLOAT", "double": "FLOAT", "real": "FLOAT", "numeric": "NUMERIC",
    "decimal": "DECIMAL", "money": "MONEY",
    "varchar": "VARCHAR", "nvarchar": "VARCHAR", "char": "CHAR", "nchar": "CHAR",
    "text": "TEXT", "ntext": "TEXT", "longtext": "TEXT", "mediumtext": "TEXT",
    "clob": "TEXT",
    "date": "DATE", "datetime": "TIMESTAMP", "timestamp": "TIMESTAMP",
    "time": "TIME", "year": "INTEGER",
    "bool": "BOOLEAN", "boolean": "BOOLEAN", "bit": "BOOLEAN",
    "blob": "BLOB", "bytea": "BLOB", "binary": "BLOB",
    "json": "JSON", "jsonb": "JSON", "uuid": "UUID",
    "serial": "INTEGER", "bigserial": "BIGINT",
}

def _normalize_type(raw: str) -> str:
    base = raw.strip().lower().split("(")[0].split(" ")[0]
    return _TYPE_MAP.get(base, raw.upper().split("(")[0].strip())


def _clean_identifier(name: str) -> str:
    return name.strip().strip("`\"[]'")


def parse_sql(sql: str) -> list[dict]:
    """Parse CREATE TABLE statements into list of table dicts."""
    tables = []

    # Normalize line endings, strip comments
    sql = re.sub(r"--[^\n]*", "", sql)
    sql = re.sub(r"/\*.*?\*/", "", sql, flags=re.DOTALL)

    # Find all CREATE TABLE blocks
    pattern = re.compile(
        r"CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?([`\"\[\w\.]+)\s*\((.*?)\)\s*(?:ENGINE|TABLESPACE|WITH|;|$)",
        re.IGNORECASE | re.DOTALL,
    )

    for match in pattern.finditer(sql):
        raw_name = _clean_identifier(match.group(1).split(".")[-1])
        body = match.group(2)

        columns = []
        primary_key = []
        foreign_keys = []

        # Split on commas that are NOT inside parentheses
        depth = 0
        current = []
        parts = []
        for ch in body:
            if ch == "(":
                depth += 1
                current.append(ch)
            elif ch == ")":
                depth -= 1
                current.append(ch)
            elif ch == "," and depth == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(ch)
        if current:
            parts.append("".join(current).strip())

        for part in parts:
            part = part.strip()
            if not part:
                continue

            upper = part.upper().lstrip()

            # PRIMARY KEY constraint
            pk_match = re.match(
                r"(?:CONSTRAINT\s+\S+\s+)?PRIMARY\s+KEY\s*\(([^)]+)\)",
                part, re.IGNORECASE,
            )
            if pk_match:
                primary_key = [_clean_identifier(c) for c in pk_match.group(1).split(",")]
                continue

            # FOREIGN KEY constraint
            fk_match = re.match(
                r"(?:CONSTRAINT\s+\S+\s+)?FOREIGN\s+KEY\s*\(([^)]+)\)\s+REFERENCES\s+([`\"\[\w\.]+)\s*\(([^)]+)\)",
                part, re.IGNORECASE,
            )
            if fk_match:
                fk_cols = [_clean_identifier(c) for c in fk_match.group(1).split(",")]
                ref_table = _clean_identifier(fk_match.group(2).split(".")[-1])
                ref_cols = [_clean_identifier(c) for c in fk_match.group(3).split(",")]
                for fc, rc in zip(fk_cols, ref_cols):
                    foreign_keys.append({
                        "column": fc,
                        "references_table": ref_table,
                        "references_column": rc,
                    })
                continue

            # Skip other constraints / indexes
            if re.match(r"(UNIQUE|INDEX|KEY|CHECK|CONSTRAINT)\s", upper):
                continue

            # Column definition
            col_match = re.match(
                r"([`\"\[\w]+)\s+(\S+(?:\s*\([^)]*\))?)(.*)",
                part, re.IGNORECASE,
            )
            if col_match:
                col_name = _clean_identifier(col_match.group(1))
                col_type = _normalize_type(col_match.group(2))
                rest = col_match.group(3).upper()
                nullable = "NOT NULL" not in rest

                # Inline PRIMARY KEY
                if "PRIMARY KEY" in rest:
                    primary_key = [col_name]

                # Inline REFERENCES
                ref_match = re.search(
                    r"REFERENCES\s+([`\"\[\w\.]+)\s*\(([^)]+)\)", part, re.IGNORECASE
                )
                if ref_match:
                    ref_table = _clean_identifier(ref_match.group(1).split(".")[-1])
                    ref_col = _clean_identifier(ref_match.group(2).split(",")[0])
                    foreign_keys.append({
                        "column": col_name,
                        "references_table": ref_table,
                        "references_column": ref_col,
                    })

                columns.append({
                    "name": col_name,
                    "data_type": col_type,
                    "nullable": nullable,
                    "description": None,
                })

        if columns:
            tables.append({
                "name": raw_name,
                "schema_name": "public",
                "columns": columns,
                "primary_key": primary_key,
                "foreign_keys": foreign_keys,
                "description": None,
            })

    return tables


# ---------------------------------------------------------------------------
# Download + process
# ---------------------------------------------------------------------------

def download(url: str, retries: int = 3) -> str | None:
    for attempt in range(retries):
        try:
            r = requests.get(url, timeout=30, headers={"User-Agent": "schemalytics-fetcher/1.0"})
            if r.status_code == 200:
                return r.text
            print(f"    HTTP {r.status_code}")
        except Exception as e:
            print(f"    attempt {attempt+1} failed: {e}")
        time.sleep(2)
    return None


def main():
    print(f"Processing {len(SOURCES)} sources -> {OUTPUT_DIR}\n")

    results = {"ok": [], "few_tables": [], "failed": []}

    for db_id, url in SOURCES:
        out_path = OUTPUT_DIR / f"{db_id}.json"
        if out_path.exists():
            tables = json.loads(out_path.read_text())["tables"]
            print(f"  SKIP {db_id} (already done, {len(tables)} tables)")
            results["ok"].append(db_id)
            continue

        print(f"  {db_id} ...")
        sql = download(url)
        if not sql:
            print(f"    FAILED to download")
            results["failed"].append(db_id)
            continue

        tables = parse_sql(sql)
        if len(tables) < 5:
            print(f"    SKIP — only {len(tables)} tables parsed (schema may be DML-only or parse failed)")
            results["few_tables"].append((db_id, len(tables)))
            continue

        schema = {"tables": tables}
        out_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
        fk_count = sum(len(t["foreign_keys"]) for t in tables)
        print(f"    OK — {len(tables)} tables, {fk_count} FKs -> {out_path.name}")
        results["ok"].append(db_id)

        time.sleep(0.5)

    print(f"\n--- Summary ---")
    print(f"  OK:          {len(results['ok'])} schemas")
    print(f"  Too few:     {results['few_tables']}")
    print(f"  Failed:      {results['failed']}")


if __name__ == "__main__":
    main()
