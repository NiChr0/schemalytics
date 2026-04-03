#!/usr/bin/env python3
"""
Auto-label classification training examples from the same schemas used for silver/gold training.

Reads from: extracted_complex, extracted, extracted_spider, extracted_new
Writes to:  finetune/labeled_silver_class/

Already-labeled files are skipped (idempotent). Run multiple times safely.

Run from repo root:
    python finetune/scripts/label_silver_classification.py
"""

import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import anthropic

EXTRACTED_DIRS = [
    Path("finetune/extracted_complex"),
    Path("finetune/extracted"),
    Path("finetune/extracted_spider"),
    Path("finetune/extracted_new"),
]
OUTPUT_DIR = Path("finetune/labeled_silver_class")
OUTPUT_DIR.mkdir(exist_ok=True)

MIN_TABLES = 3    # skip trivial schemas
BATCH_SIZE = 30   # max tables per API call — smaller batches prevent truncation on large schemas
SKIP_PREFIXES = ('gretelai_',)  # synthetic mega-schemas — skip to save credits

SYSTEM_PROMPT = (
    'You are a data modelling expert who classifies database tables as "fact", "dimension", "bridge", or "reference".\n\n'
    'You receive:\n'
    '  1. The full database schema with column and FK details.\n'
    '  2. Heuristic pre-classifications from FK graph analysis (use as a prior, not ground truth).\n'
    '  3. Business context (industry, metrics, goals).\n\n'
    'Your job is to validate the heuristic results, correct misclassifications, and assign a confidence\n'
    'score (1\u20133) to each table. Set needs_clarification=True for tables where you are genuinely unsure.\n\n'
    'Definitions:\n'
    '  - FACT: Records a business event or transaction. Has a date column + measures (quantities, amounts,\n'
    '    rates) + FKs to dimensions. Examples: order_details, orders, transactions, events, sessions.\n'
    '  - DIMENSION: Describes a business entity. Has many descriptive text/categorical attributes. May have\n'
    '    outgoing FKs to other dimensions (snowflake). Examples: customers, products, employees, categories.\n'
    '  - BRIDGE: Resolves a many-to-many relationship. Has ONLY two FK columns (+ maybe a surrogate key)\n'
    '    and almost NO other attributes. Examples: employee_territories, user_roles, product_tags.\n'
    '  - REFERENCE: Small standalone lookup table with no FKs in or out. Examples: us_states, currencies,\n'
    '    status_codes, country_codes.\n\n'
    'Critical rules \u2014 override heuristics when these apply:\n'
    '  1. A PRODUCT/ITEM CATALOG is always a DIMENSION, even if it has outgoing FKs to categories or\n'
    '     suppliers. Having outgoing FKs to lookup tables = snowflake pattern, not a fact.\n'
    '  2. An EMPLOYEE or PERSON table is always a DIMENSION, even with a self-referencing FK (reports_to)\n'
    '     or outgoing FKs to a region/department table.\n'
    '  3. A true BRIDGE has almost no columns beyond its two FK columns. If a table has 3+ non-FK\n'
    '     descriptive attributes (names, descriptions, amounts), it is a DIMENSION or FACT, not a bridge.\n'
    '  4. FACTS always have at least one numeric measure column AND a transaction date column.\n'
    '     "Header" tables (e.g. salesorderheader, purchaseorderheader) ARE facts \u2014 they record a\n'
    '     business transaction event with a date and monetary amounts. Association tables with NO\n'
    '     numeric measures and NO transaction date are BRIDGE, not fact.\n'
    '  5. Reference/lookup tables (e.g. us_states, region) with no transactional data are REFERENCE.\n\n'
    'Examples (Northwind-style schema):\n'
    '  order_details(order_id\u2192orders, product_id\u2192products, unit_price, quantity, discount) \u2192 FACT\n'
    '    reason: has measures + FKs to dimensions, records order line events\n'
    '  products(product_id, product_name, category_id\u2192categories, supplier_id\u2192suppliers, unit_price) \u2192 DIMENSION\n'
    '    reason: entity descriptor; outgoing FKs to lookup tables = snowflake, not a fact\n'
    '  employees(employee_id, name, hire_date, reports_to\u2192employees) \u2192 DIMENSION\n'
    '    reason: entity descriptor; self-referencing FK does not make it a fact or bridge\n'
    '  employee_territories(employee_id\u2192employees, territory_id\u2192territories) \u2192 BRIDGE\n'
    '    reason: exactly 2 FK columns, no descriptive attributes, resolves many-to-many\n'
    '  us_states(state_id, state_name, region_id) \u2192 REFERENCE\n'
    '    reason: small static lookup with no transactional data\n\n'
    'Output format: keep each `reasoning` to \u22648 words.\n'
)

JSON_ONLY_SUFFIX = '\n\nIMPORTANT: Output ONLY the JSON. No markdown, no explanation, no code fences. Start your response with { or [.'

DATE_TYPES = {'DATE', 'DATETIME', 'TIMESTAMP', 'TIMESTAMPTZ', 'TIME'}
MEASURE_TYPES = {'INTEGER', 'INT', 'BIGINT', 'SMALLINT', 'REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL', 'MONEY'}


def is_date_col(col: dict) -> bool:
    return any(d in col['data_type'].upper() for d in DATE_TYPES)


def is_measure_col(col: dict) -> bool:
    return any(m in col['data_type'].upper() for m in MEASURE_TYPES)


def heuristic_classify(table: dict) -> tuple[str, str, str]:
    fks_out = len(table['foreign_keys'])
    fk_col_names = {fk['column'] for fk in table['foreign_keys']}
    non_fk_cols = [c for c in table['columns'] if c['name'] not in fk_col_names
                   and c['name'] not in table['primary_key']]
    has_date = any(is_date_col(c) for c in table['columns'])
    has_measure = any(is_measure_col(c) for c in non_fk_cols)

    if fks_out >= 2 and len(non_fk_cols) <= 1:
        return 'bridge', 'medium', 'Only FK columns; likely many-to-many resolver.'
    if fks_out >= 1 and has_date and has_measure:
        return 'fact', 'high', 'Has FKs + date + measures; records a transaction event.'
    if fks_out == 0:
        if len(table['columns']) <= 5 and not has_date:
            return 'reference', 'medium', 'No FKs; small standalone lookup table.'
        return 'dimension', 'medium', 'No FKs; descriptive entity attributes.'
    return 'dimension', 'medium', f'Has {fks_out} outgoing FK(s), no transaction date; likely snowflake dimension.'


def build_user_message(db_id: str, tables: list) -> str:
    lines = ['Database schema:']
    for t in tables:
        fk_map = {fk['column']: fk['references_table'] for fk in t['foreign_keys']}
        col_parts = []
        for c in t['columns']:
            col_parts.append(f"{c['name']}\u2192{fk_map[c['name']]}" if c['name'] in fk_map else c['name'])
        lines.append(f"  {t['name']}({', '.join(col_parts)})")

    lines.append('')
    lines.append('Heuristic pre-classifications:')
    for t in tables:
        role, conf, reason = heuristic_classify(t)
        lines.append(f'  {t["name"]}: {role} (confidence={conf}) \u2014 {reason}')

    lines.append('')
    lines.append(f'Business context: Database "{db_id}". Domain inferred from table/column names.')
    return '\n'.join(lines)


def _parse_response(raw: str) -> list:
    """Parse API response into a list of normalized classification dicts."""
    arr_start = raw.find('[')
    obj_start = raw.find('{')
    if arr_start == -1 and obj_start == -1:
        raise ValueError(f"No JSON in response: {repr(raw[:200])}")

    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        parsed = json.loads(raw[arr_start:raw.rfind(']') + 1])
        return [{
            'table_name': item.get('table_name') or item.get('table') or item.get('name', ''),
            'role': (item.get('role') or item.get('classification') or item.get('type', 'dimension')).lower(),
            'confidence': item.get('confidence', 2),
            'reasoning': item.get('reasoning', ''),
            'needs_clarification': item.get('needs_clarification', False),
        } for item in parsed]
    else:
        parsed = json.loads(raw[obj_start:raw.rfind('}') + 1])
        items = parsed.get('classifications', [])
        for item in items:
            for old, new in [('table', 'table_name'), ('classification', 'role'), ('type', 'role')]:
                if old in item and new not in item:
                    item[new] = item.pop(old)
            if 'role' in item:
                item['role'] = item['role'].lower()
        return items


def _call_api(client: anthropic.Anthropic, db_id: str, batch: list) -> list:
    user_msg = build_user_message(db_id, batch)
    messages = [{'role': 'user', 'content': user_msg}]
    for model in ('claude-haiku-4-5-20251001', 'claude-sonnet-4-6'):
        response = client.messages.create(
            model=model,
            max_tokens=4096,
            system=SYSTEM_PROMPT + JSON_ONLY_SUFFIX,
            messages=messages,
        )
        raw = next((b.text for b in response.content if hasattr(b, 'text')), '')
        try:
            return _parse_response(raw)
        except Exception:
            if model == 'claude-sonnet-4-6':
                raise
            print(f'  [fallback to Sonnet] {db_id}')
    raise RuntimeError('unreachable')


def label_schema(client: anthropic.Anthropic, db_id: str, tables: list) -> list:
    """Label all tables, returning one training record per batch."""
    records = []
    for i in range(0, len(tables), BATCH_SIZE):
        batch = tables[i:i + BATCH_SIZE]
        classifications = _call_api(client, db_id, batch)
        records.append({
            'messages': [
                {'role': 'system', 'content': SYSTEM_PROMPT},
                {'role': 'user', 'content': build_user_message(db_id, batch)},
                {'role': 'assistant', 'content': json.dumps({'classifications': classifications})},
            ]
        })
        if i + BATCH_SIZE < len(tables):
            time.sleep(0.3)
    return records


WORKERS = 5  # concurrent API calls


def _process_one(client: anthropic.Anthropic, path: Path, idx: int, total: int) -> tuple[str, str]:
    """Label one schema file. Returns (stem, status_line)."""
    out_path = OUTPUT_DIR / path.name.replace('.json', '.jsonl')
    if out_path.exists():
        return path.stem, 'skip'

    if any(path.stem.startswith(p) for p in SKIP_PREFIXES):
        return path.stem, 'skip'

    data = json.loads(path.read_text(encoding='utf-8'))
    tables = data.get('tables', [])
    if len(tables) < MIN_TABLES:
        return path.stem, f'skip_trivial:{len(tables)}'

    records = label_schema(client, path.stem, tables)
    out_path.write_text('\n'.join(json.dumps(r) for r in records) + '\n', encoding='utf-8')
    return path.stem, f'ok:{len(tables)}:{len(records)}'


def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')

    client = anthropic.Anthropic(api_key=api_key)

    seen: set[str] = set()
    schema_files: list[Path] = []
    for d in EXTRACTED_DIRS:
        if not d.exists():
            print(f'Skipping missing dir: {d}')
            continue
        for path in sorted(d.glob('*.json')):
            if path.stem not in seen:
                seen.add(path.stem)
                schema_files.append(path)

    total = len(schema_files)
    print(f'Found {total} unique schemas — running {WORKERS} workers in parallel')

    done = skipped = 0
    errors: list[str] = []
    completed = 0

    with ThreadPoolExecutor(max_workers=WORKERS) as pool:
        futures = {
            pool.submit(_process_one, client, path, i, total): (i, path)
            for i, path in enumerate(schema_files)
        }
        for future in as_completed(futures):
            i, path = futures[future]
            completed += 1
            try:
                stem, status = future.result()
                if status == 'skip':
                    skipped += 1
                elif status.startswith('skip_trivial'):
                    n = status.split(':')[1]
                    print(f'  [{completed}/{total}] SKIP {stem} ({n} tables < {MIN_TABLES})')
                    skipped += 1
                else:
                    _, n_tables, n_records = status.split(':')
                    print(f'  [{completed}/{total}] OK   {stem} ({n_tables} tables, {n_records} records)')
                    done += 1
            except Exception as e:
                print(f'  [{completed}/{total}] ERR  {path.stem}: {e}')
                errors.append(path.stem)

    print(f'\nDone. labeled={done}  skipped={skipped}  errors={len(errors)}')
    if errors:
        print('Failed:', errors)


if __name__ == '__main__':
    main()
