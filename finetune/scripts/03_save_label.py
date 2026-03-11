#!/usr/bin/env python3
"""
Save a Claude.ai label response as a JSONL training example.

Run from repo root:
    python finetune/scripts/03_save_label.py \\
        --schema finetune/extracted/sakila.json \\
        --output finetune/labeled/sakila.jsonl \\
        --label '{"classifications": [...]}'

Or read label from stdin (e.g. pbpaste):
    pbpaste | python finetune/scripts/03_save_label.py \\
        --schema finetune/extracted/sakila.json \\
        --output finetune/labeled/sakila.jsonl
"""

import argparse
import json
import sys
from pathlib import Path

from pydantic import BaseModel, ValidationError

from schemalytics.models import PipelineContext, Schema, TableClassificationResult
from schemalytics.planner import (
    _AGENT3_SYSTEM,
    _compact_schema_summary,
    _heuristic_summary,
    classify_by_fk_graph,
)


class _ClassificationList(BaseModel):
    classifications: list[TableClassificationResult]


def main() -> None:
    parser = argparse.ArgumentParser(description="Save a label as a JSONL training example.")
    parser.add_argument("--schema", required=True, help="Path to extracted schema JSON")
    parser.add_argument("--output", required=True, help="Path to output JSONL file (appended)")
    parser.add_argument("--label", default=None, help="Label JSON string (omit to read from stdin)")
    args = parser.parse_args()

    schema_path = Path(args.schema)
    if not schema_path.exists():
        print(f"ERROR: Schema file not found: {schema_path}", file=sys.stderr)
        sys.exit(1)

    # Read label
    if args.label:
        label_raw = args.label
    else:
        print("Reading label from stdin...", file=sys.stderr)
        label_raw = sys.stdin.read().strip()

    if not label_raw:
        print("ERROR: No label provided (use --label or pipe via stdin)", file=sys.stderr)
        sys.exit(1)

    # Parse and validate label
    try:
        label_json = json.loads(label_raw)
    except json.JSONDecodeError as e:
        print(f"ERROR: Label is not valid JSON: {e}", file=sys.stderr)
        sys.exit(1)

    try:
        validated = _ClassificationList.model_validate(label_json)
    except ValidationError as e:
        print(f"ERROR: Label failed Pydantic validation:\n{e}", file=sys.stderr)
        sys.exit(1)

    # Load schema and reconstruct the exact user message
    schema = Schema.model_validate_json(schema_path.read_text())
    ctx = PipelineContext(
        industry="unknown",
        business_type="unknown",
        metrics=[],
        goals=[],
        grain="unknown",
        table_classifications=[],
    )

    heuristics = classify_by_fk_graph(schema)
    compact_summary = _compact_schema_summary(schema)
    heuristic_summary = _heuristic_summary(heuristics)

    base_context = (
        f"Database schema:\n{compact_summary}\n\n"
        f"Heuristic pre-classifications:\n{heuristic_summary}\n\n"
        f"Business context:\n"
        f"  Industry: {ctx.industry} / {ctx.business_type}\n"
        f"  Metrics:  {', '.join(ctx.metrics)}\n"
        f"  Goals:    {', '.join(ctx.goals)}"
    )

    all_table_names = [t.name for t in schema.tables]
    user_message = (
        base_context
        + f"\n\nClassify ONLY these {len(all_table_names)} tables "
        f"(skip all others): {all_table_names}"
    )

    # Build JSONL record in MLX-LM chat format
    assistant_content = validated.model_dump_json()
    record = {
        "messages": [
            {"role": "system", "content": _AGENT3_SYSTEM},
            {"role": "user", "content": user_message},
            {"role": "assistant", "content": assistant_content},
        ]
    }

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")

    n_tables = len(validated.classifications)
    print(f"Saved 1 example ({n_tables} table classifications) → {output_path}")


if __name__ == "__main__":
    main()
