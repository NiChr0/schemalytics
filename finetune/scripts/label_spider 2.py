#!/usr/bin/env python3
"""
Auto-label Spider schemas using Claude Sonnet via Anthropic API.

Run from repo root:
    python finetune/scripts/label_spider.py
"""

import json
import os
import re
import time
from pathlib import Path
import anthropic

EXTRACTED_DIR = Path("finetune/extracted_spider")
OUTPUT_DIR = Path("finetune/labeled_spider")
OUTPUT_DIR.mkdir(exist_ok=True)

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
    'Additional examples (AdventureWorks-style schema):\n'
    '  salesorderheader(salesorderid, customerid\u2192customer, orderdate, subtotal, taxamt, totaldue) \u2192 FACT\n'
    '    reason: records sales transaction event; has date + monetary amounts\n'
    '  purchaseorderheader(purchaseorderid, vendorid\u2192vendor, orderdate, totaldue, freight) \u2192 FACT\n'
    '    reason: records procurement event; has date + monetary amounts\n'
    '  shoppingcartitem(shoppingcartitemid, shoppingcartid, productid\u2192product, quantity, datecreated) \u2192 FACT\n'
    '    reason: records cart-add event; has date + quantity measure\n'
    '  workorder(workorderid, productid\u2192product, orderqty, scrappedqty, startdate, duedate) \u2192 FACT\n'
    '    reason: records manufacturing event; has dates + quantity measures\n'
    '  businessentityaddress(businessentityid\u2192entity, addressid\u2192address, addresstypeid\u2192addresstype) \u2192 BRIDGE\n'
    '    reason: pure association table; no numeric measures, no transaction date\n\n'
    'Output format: keep each `reasoning` to \u22648 words.\n'
)

DATE_TYPES = {'DATE', 'DATETIME', 'TIMESTAMP', 'TIMESTAMPTZ', 'TIME'}
MEASURE_TYPES = {'INTEGER', 'INT', 'BIGINT', 'SMALLINT', 'REAL', 'FLOAT', 'DOUBLE', 'NUMERIC', 'DECIMAL', 'MONEY'}


def is_date_col(col: dict) -> bool:
    return any(d in col['data_type'].upper() for d in DATE_TYPES)


def is_measure_col(col: dict) -> bool:
    return any(m in col['data_type'].upper() for m in MEASURE_TYPES)


def heuristic_classify(table: dict, all_tables: list) -> tuple[str, str]:
    """Returns (role, confidence_str, reason) using FK graph heuristics."""
    fks_out = len(table['foreign_keys'])
    fk_col_names = {fk['column'] for fk in table['foreign_keys']}
    non_fk_cols = [c for c in table['columns'] if c['name'] not in fk_col_names
                   and c['name'] not in table['primary_key']]

    has_date = any(is_date_col(c) for c in table['columns'])
    has_measure = any(is_measure_col(c) for c in non_fk_cols)

    # Bridge: only FK cols + PK, minimal other attributes
    if fks_out >= 2 and len(non_fk_cols) <= 1:
        return 'bridge', 'medium', 'Only FK columns; likely many-to-many resolver.'

    # Fact: has FKs + date + measures
    if fks_out >= 1 and has_date and has_measure:
        return 'fact', 'high', 'Has FKs + date + measures; records a transaction event.'

    # No FKs at all — reference or standalone dimension
    if fks_out == 0:
        if len(table['columns']) <= 5 and not has_date:
            return 'reference', 'medium', 'No FKs; small standalone lookup table.'
        return 'dimension', 'medium', 'No FKs; descriptive entity attributes.'

    # Has FKs but no date — dimension (snowflake) or bridge
    return 'dimension', 'medium', f'Has {fks_out} outgoing FK(s), no transaction date; likely snowflake dimension.'


def build_user_message(db_id: str, tables: list) -> str:
    # Schema summary
    lines = ['Database schema:']
    for t in tables:
        col_parts = []
        fk_map = {fk['column']: fk['references_table'] for fk in t['foreign_keys']}
        for c in t['columns']:
            if c['name'] in fk_map:
                col_parts.append(f"{c['name']}\u2192{fk_map[c['name']]}")
            else:
                col_parts.append(c['name'])
        lines.append(f"  {t['name']}({', '.join(col_parts)})")

    lines.append('')
    lines.append('Heuristic pre-classifications:')
    for t in tables:
        role, conf, reason = heuristic_classify(t, tables)
        lines.append(f'  {t["name"]}: {role} (confidence={conf}) \u2014 {reason}')

    lines.append('')
    lines.append(f'Business context: Spider benchmark database "{db_id}". Domain inferred from table/column names.')

    return '\n'.join(lines)


JSON_ONLY_SUFFIX = '\n\nIMPORTANT: Output ONLY the JSON. No markdown, no explanation, no code fences. Start your response with { or [.'


def label_schema(client: anthropic.Anthropic, db_id: str, tables: list) -> dict:
    user_msg = build_user_message(db_id, tables)
    response = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=4096,
        system=SYSTEM_PROMPT + JSON_ONLY_SUFFIX,
        messages=[{'role': 'user', 'content': user_msg}],
    )
    raw = next((b.text for b in response.content if hasattr(b, 'text')), '')

    # Extract JSON — could be array [...] or object {...}
    arr_start = raw.find('[')
    obj_start = raw.find('{')
    if arr_start == -1 and obj_start == -1:
        raise ValueError(f"No JSON in response: {repr(raw[:200])}")

    if arr_start != -1 and (obj_start == -1 or arr_start < obj_start):
        # Response is a JSON array
        end = raw.rfind(']')
        parsed = json.loads(raw[arr_start:end + 1])
        # Normalize field names: table/name -> table_name, classification/type -> role
        normalized = []
        for item in parsed:
            normalized.append({
                'table_name': item.get('table_name') or item.get('table') or item.get('name', ''),
                'role': (item.get('role') or item.get('classification') or item.get('type', 'dimension')).lower(),
                'confidence': item.get('confidence', 2),
                'reasoning': item.get('reasoning', ''),
                'needs_clarification': item.get('needs_clarification', False),
            })
        assistant_content = json.dumps({'classifications': normalized})
    else:
        # Response is a JSON object
        end = raw.rfind('}')
        parsed = json.loads(raw[obj_start:end + 1])
        # Normalize if using non-standard field names
        if 'classifications' in parsed:
            for item in parsed['classifications']:
                if 'table' in item and 'table_name' not in item:
                    item['table_name'] = item.pop('table')
                if 'classification' in item and 'role' not in item:
                    item['role'] = item.pop('classification')
                if 'type' in item and 'role' not in item:
                    item['role'] = item.pop('type')
                if 'role' in item:
                    item['role'] = item['role'].lower()
        assistant_content = json.dumps(parsed)

    return {
        'messages': [
            {'role': 'system', 'content': SYSTEM_PROMPT},
            {'role': 'user', 'content': user_msg},
            {'role': 'assistant', 'content': assistant_content},
        ]
    }


def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')

    client = anthropic.Anthropic(api_key=api_key)

    schema_files = sorted(EXTRACTED_DIR.glob('*.json'))
    print(f'Labeling {len(schema_files)} schemas...')

    errors = []
    for i, path in enumerate(schema_files):
        out_path = OUTPUT_DIR / path.name.replace('.json', '.jsonl')
        if out_path.exists():
            print(f'  [{i+1}/{len(schema_files)}] SKIP {path.stem} (already done)')
            continue

        data = json.loads(path.read_text(encoding='utf-8'))
        tables = data.get('tables', [])
        if not tables:
            print(f'  [{i+1}/{len(schema_files)}] SKIP {path.stem} (empty)')
            continue

        try:
            record = label_schema(client, path.stem, tables)
            out_path.write_text(json.dumps(record) + '\n', encoding='utf-8')
            print(f'  [{i+1}/{len(schema_files)}] OK   {path.stem} ({len(tables)} tables)')
        except Exception as e:
            print(f'  [{i+1}/{len(schema_files)}] ERR  {path.stem}: {e}')
            errors.append(path.stem)

        # Avoid rate limits
        time.sleep(0.3)

    print(f'\nDone. Errors: {len(errors)}')
    if errors:
        print('Failed:', errors)


if __name__ == '__main__':
    main()
