#!/usr/bin/env python3
"""
Download and extract complex real-world SQL schemas into our JSON format.

Sources:
  1. AdventureWorks for PostgreSQL (~70 tables, ERP)
  2. PrestaShop (~100 tables, e-commerce)
  3. OpenCart (~70 tables, e-commerce)
  4. MediaWiki (~40 tables, CMS)
  5. gretelai/synthetic_text_to_sql (100+ domains, multi-table schemas)

Run from repo root:
    python finetune/scripts/download_and_extract_complex.py
"""

import json
import re
import urllib.request
from pathlib import Path

try:
    from datasets import load_dataset
    HF_AVAILABLE = True
except ImportError:
    HF_AVAILABLE = False
    print("WARNING: 'datasets' not installed — skipping gretelai source.")

OUTPUT_DIR = Path("finetune/extracted_complex")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# SQL parser (handles both MySQL and PostgreSQL dialects)
# ---------------------------------------------------------------------------

DATE_KEYWORDS   = {'DATE', 'DATETIME', 'TIMESTAMP', 'TIMESTAMPTZ', 'TIME', 'YEAR'}
NUMBER_KEYWORDS = {'INT', 'INTEGER', 'BIGINT', 'SMALLINT', 'TINYINT', 'MEDIUMINT',
                   'REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL', 'MONEY', 'SERIAL',
                   'BIGSERIAL', 'SMALLSERIAL'}


def normalize_type(raw: str) -> str:
    """Strip width/precision, uppercase."""
    return re.sub(r'\(.*\)', '', raw).upper().strip().rstrip(',')


def parse_create_table(sql: str) -> dict | None:
    """Parse a single CREATE TABLE statement into schema dict."""
    name_match = re.search(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?(\w+)[`"\]]?\s*\(',
        sql, re.IGNORECASE
    )
    if not name_match:
        return None
    table_name = name_match.group(1)

    inner_match = re.search(r'\((.+)\)', sql, re.DOTALL)
    if not inner_match:
        return None
    inner = inner_match.group(1)

    # Split by commas, respecting nested parens
    parts, depth, current = [], 0, ''
    for ch in inner:
        if ch == '(':
            depth += 1; current += ch
        elif ch == ')':
            depth -= 1; current += ch
        elif ch == ',' and depth == 0:
            parts.append(current.strip()); current = ''
        else:
            current += ch
    if current.strip():
        parts.append(current.strip())

    columns, primary_key, foreign_keys = [], [], []

    for part in parts:
        part = part.strip()
        if not part:
            continue
        upper = part.upper().lstrip()

        # Skip MySQL index/key lines that aren't column definitions
        if re.match(r'(UNIQUE\s+)?KEY\s+', upper) or \
           re.match(r'(FULLTEXT|SPATIAL)\s+', upper):
            continue

        if upper.startswith('PRIMARY KEY'):
            pks = re.findall(r'[`"\[]?(\w+)[`"\]]?', part[len('PRIMARY KEY'):])
            primary_key.extend(pks)
            continue

        if upper.startswith('FOREIGN KEY'):
            fk_col = re.search(r'FOREIGN\s+KEY\s*\([`"\[]?(\w+)[`"\]]?\)', part, re.IGNORECASE)
            ref     = re.search(r'REFERENCES\s+[`"\[]?(\w+)[`"\]]?\s*\([`"\[]?(\w+)[`"\]]?\)', part, re.IGNORECASE)
            if fk_col and ref:
                foreign_keys.append({
                    'column': fk_col.group(1),
                    'references_table': ref.group(1),
                    'references_column': ref.group(2),
                })
            continue

        if re.match(r'(UNIQUE|INDEX|CHECK|CONSTRAINT|KEY)\b', upper):
            continue

        # Column definition
        col_match = re.match(r'[`"\[]?(\w+)[`"\]]?\s+(\S+)', part)
        if col_match:
            col_name = col_match.group(1)
            data_type = normalize_type(col_match.group(2))
            nullable = 'NOT NULL' not in upper
            columns.append({
                'name': col_name,
                'data_type': data_type,
                'nullable': nullable,
                'description': None,
            })

    if not columns:
        return None

    return {
        'name': table_name,
        'schema_name': 'public',
        'columns': columns,
        'primary_key': primary_key,
        'foreign_keys': foreign_keys,
        'description': None,
    }


def parse_sql_file(sql_text: str) -> list[dict]:
    """Extract all CREATE TABLE statements from a SQL file."""
    # Remove comments
    sql_text = re.sub(r'--[^\n]*', '', sql_text)
    sql_text = re.sub(r'/\*.*?\*/', '', sql_text, flags=re.DOTALL)

    # Find all CREATE TABLE blocks
    tables = []
    for match in re.finditer(
        r'CREATE\s+TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?[`"\[]?\w+[`"\]]?\s*\([^;]+;',
        sql_text, re.IGNORECASE | re.DOTALL
    ):
        t = parse_create_table(match.group(0))
        if t and t['columns']:
            tables.append(t)
    return tables


def download_and_save(name: str, url: str, description: str = ''):
    out_path = OUTPUT_DIR / f'{name}.json'
    if out_path.exists():
        print(f'  SKIP {name} (already extracted)')
        return

    print(f'  Downloading {name} from GitHub...')
    try:
        req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=30) as resp:
            sql_text = resp.read().decode('utf-8', errors='replace')
    except Exception as e:
        print(f'  ERR  {name}: {e}')
        return

    tables = parse_sql_file(sql_text)
    if not tables:
        print(f'  ERR  {name}: no tables parsed')
        return

    out_path.write_text(json.dumps({'tables': tables}, indent=2), encoding='utf-8')
    print(f'  OK   {name}: {len(tables)} tables')


# ---------------------------------------------------------------------------
# GitHub sources
# ---------------------------------------------------------------------------

GITHUB_SOURCES = [
    # E-commerce
    (
        'prestashop',
        'https://raw.githubusercontent.com/PrestaShop/PrestaShop/develop/install-dev/data/db_structure.sql',
    ),
    (
        'opencart',
        'https://raw.githubusercontent.com/opencart/opencart/3.0.3.8/upload/install/opencart.sql',
    ),
    # ERP / CRM / ITSM
    (
        'northwind',
        'https://raw.githubusercontent.com/pthom/northwind_psql/master/northwind.sql',
    ),
    (
        'glpi',
        'https://raw.githubusercontent.com/glpi-project/glpi/main/install/mysql/glpi-empty.sql',
    ),
    # Healthcare
    (
        'openemr',
        'https://raw.githubusercontent.com/openemr/openemr/master/sql/database.sql',
    ),
    # Monitoring / Infra
    (
        'icinga',
        'https://raw.githubusercontent.com/Icinga/icingadb/main/schema/mysql/schema.sql',
    ),
    # CMS / Collaboration
    (
        'typo3',
        'https://raw.githubusercontent.com/TYPO3/typo3/main/typo3/sysext/core/ext_tables.sql',
    ),
    (
        'roundcube',
        'https://raw.githubusercontent.com/roundcube/roundcubemail/master/SQL/mysql.initial.sql',
    ),
]


# ---------------------------------------------------------------------------
# gretelai/synthetic_text_to_sql — extract diverse multi-table schemas
# ---------------------------------------------------------------------------

def extract_gretelai(max_schemas: int = 1000, min_tables: int = 6):
    if not HF_AVAILABLE:
        return

    print(f'  Streaming gretelai/synthetic_text_to_sql (grouping by domain, min_tables={min_tables})...')
    try:
        ds = load_dataset('gretelai/synthetic_text_to_sql', split='train', streaming=True)
    except Exception as e:
        print(f'  ERR  gretelai: {e}')
        return

    # Group tables by domain — each row has 1-2 tables; merge all rows for a domain
    domain_tables: dict[str, dict[str, dict]] = {}  # domain -> {table_name -> table_dict}

    for row in ds:
        domain = row.get('domain', '').strip()
        ctx = row.get('sql_context', '')
        if not domain or not ctx:
            continue
        tables = parse_sql_file(ctx)
        if not tables:
            continue
        if domain not in domain_tables:
            domain_tables[domain] = {}
        for t in tables:
            domain_tables[domain][t['name']] = t

    # Filter to domains with enough tables
    schemas = []
    for domain, table_map in sorted(domain_tables.items()):
        tables = list(table_map.values())
        if len(tables) < min_tables:
            continue
        fk_count = sum(len(t['foreign_keys']) for t in tables)
        if fk_count < 2:
            continue
        schemas.append({'db_id': f"gretelai_{len(schemas):04d}", 'domain': domain, 'tables': tables})
        if len(schemas) >= max_schemas:
            break

    if not schemas:
        print('  ERR  gretelai: no qualifying schemas found after grouping by domain')
        return

    saved = 0
    for s in schemas:
        p = OUTPUT_DIR / f"{s['db_id']}.json"
        if p.exists():
            continue
        p.write_text(json.dumps({'tables': s['tables']}, indent=2), encoding='utf-8')
        saved += 1

    print(f'  OK   gretelai: {saved} new schemas saved ({len(schemas)} total qualifying, {len(domain_tables)} domains seen)')


# ---------------------------------------------------------------------------

def main():
    print(f'Extracting complex schemas to {OUTPUT_DIR}/')
    print()

    print('GitHub sources:')
    for name, url in GITHUB_SOURCES:
        download_and_save(name, url)

    print('\ngretelai/synthetic_text_to_sql:')
    extract_gretelai(max_schemas=1000, min_tables=6)

    total = len(list(OUTPUT_DIR.glob('*.json')))
    print(f'\nDone. {total} schema files in {OUTPUT_DIR}/')


if __name__ == '__main__':
    main()
