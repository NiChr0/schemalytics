#!/usr/bin/env python3
"""
Auto-label complex schemas using Claude Sonnet via Anthropic API.

Run from repo root:
    python finetune/scripts/label_complex.py
"""

import json
import os
import time
from pathlib import Path
import anthropic

# Reuse the same heuristic + labeling logic from label_spider.py
import sys
sys.path.insert(0, str(Path(__file__).parent))
from label_spider import SYSTEM_PROMPT, JSON_ONLY_SUFFIX, heuristic_classify, build_user_message, label_schema

EXTRACTED_DIR = Path("finetune/extracted_complex")
OUTPUT_DIR    = Path("finetune/labeled_complex")
OUTPUT_DIR.mkdir(exist_ok=True)

CHUNK_SIZE = 30  # Max tables per API call — keeps prompt within context limits


def label_schema_chunked(client, db_id: str, tables: list) -> list:
    """Label a large schema by splitting into chunks of CHUNK_SIZE tables.
    Returns a list of JSONL records (one per chunk).
    """
    if len(tables) <= CHUNK_SIZE:
        return [label_schema(client, db_id, tables)]

    records = []
    for chunk_i, start in enumerate(range(0, len(tables), CHUNK_SIZE)):
        chunk = tables[start:start + CHUNK_SIZE]
        chunk_id = f"{db_id}_chunk{chunk_i}"
        record = label_schema(client, chunk_id, chunk)
        records.append(record)
        time.sleep(0.5)
    return records


def main():
    api_key = os.environ.get('ANTHROPIC_API_KEY')
    if not api_key:
        raise RuntimeError('ANTHROPIC_API_KEY not set')

    client = anthropic.Anthropic(api_key=api_key)

    schema_files = sorted(EXTRACTED_DIR.glob('*.json'))
    print(f'Labeling {len(schema_files)} complex schemas...')

    errors = []
    for i, path in enumerate(schema_files):
        data = json.loads(path.read_text(encoding='utf-8'))
        tables = data.get('tables', [])
        if not tables:
            print(f'  [{i+1}/{len(schema_files)}] SKIP {path.stem} (empty)')
            continue

        # For chunked schemas, check if ALL chunks are already done
        n_chunks = max(1, (len(tables) + CHUNK_SIZE - 1) // CHUNK_SIZE)
        if n_chunks == 1:
            out_path = OUTPUT_DIR / f'{path.stem}.jsonl'
            if out_path.exists():
                print(f'  [{i+1}/{len(schema_files)}] SKIP {path.stem} (already done)')
                continue
        else:
            all_done = all(
                (OUTPUT_DIR / f'{path.stem}_chunk{c}.jsonl').exists()
                for c in range(n_chunks)
            )
            if all_done:
                print(f'  [{i+1}/{len(schema_files)}] SKIP {path.stem} (all {n_chunks} chunks done)')
                continue

        try:
            records = label_schema_chunked(client, path.stem, tables)
            if len(records) == 1:
                out_path = OUTPUT_DIR / f'{path.stem}.jsonl'
                out_path.write_text(json.dumps(records[0]) + '\n', encoding='utf-8')
            else:
                for chunk_i, record in enumerate(records):
                    out_path = OUTPUT_DIR / f'{path.stem}_chunk{chunk_i}.jsonl'
                    if not out_path.exists():
                        out_path.write_text(json.dumps(record) + '\n', encoding='utf-8')
            chunks_str = f' ({len(records)} chunks)' if len(records) > 1 else ''
            print(f'  [{i+1}/{len(schema_files)}] OK   {path.stem} ({len(tables)} tables{chunks_str})')
        except Exception as e:
            print(f'  [{i+1}/{len(schema_files)}] ERR  {path.stem}: {e}')
            errors.append(path.stem)

        time.sleep(0.5)

    print(f'\nDone. Errors: {len(errors)}')
    if errors:
        print('Failed:', errors)


if __name__ == '__main__':
    main()
