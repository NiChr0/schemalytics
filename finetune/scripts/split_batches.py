#!/usr/bin/env python3
"""
Re-split labeled JSONL examples into 20-table batches, matching production classify_tables().
This keeps sequences under 2048 tokens and makes training much faster.

Run from repo root:
    python finetune/scripts/split_batches.py
"""

import json
from pathlib import Path

from pydantic import BaseModel
from schemalytics.models import PipelineContext, Schema, TableClassificationResult
from schemalytics.planner import (
    _AGENT3_SYSTEM,
    _AGENT3_BATCH_SIZE,
    _compact_schema_summary,
    _heuristic_summary,
    classify_by_fk_graph,
)

LABELED_DIR = Path("finetune/labeled")
OUTPUT_DIR = Path("finetune/labeled_batched")
OUTPUT_DIR.mkdir(exist_ok=True)

class _ClassificationList(BaseModel):
    classifications: list[TableClassificationResult]

ctx = PipelineContext(
    industry="unknown", business_type="unknown",
    metrics=[], goals=[], grain="unknown", table_classifications=[],
)


def split_example(record: dict) -> list[dict]:
    """Split a single full-schema example into 20-table batch examples."""
    messages = record["messages"]
    assistant_content = messages[2]["content"]
    label = _ClassificationList.model_validate_json(assistant_content)

    # Recover schema name from the user message (first line has schema summary)
    # We need to reload the schema — find it by matching table names in the label
    all_tables = [c.table_name for c in label.classifications]

    # Find the matching extracted schema file
    schema_file = None
    for path in Path("finetune/extracted").glob("*.json"):
        schema = Schema.model_validate_json(path.read_text())
        schema_table_names = {t.name for t in schema.tables}
        if set(all_tables) <= schema_table_names:
            schema_file = path
            break

    if schema_file is None:
        print(f"  WARNING: could not find schema for tables {all_tables[:3]}... skipping")
        return [record]  # return original if we can't split

    schema = Schema.model_validate_json(schema_file.read_text())
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

    # Build label lookup
    label_map = {c.table_name: c for c in label.classifications}

    # Split into batches of AGENT3_BATCH_SIZE
    batched_records = []
    table_names = [c.table_name for c in label.classifications]
    for i in range(0, len(table_names), _AGENT3_BATCH_SIZE):
        batch_names = table_names[i:i + _AGENT3_BATCH_SIZE]
        batch_labels = [label_map[n] for n in batch_names if n in label_map]
        if not batch_labels:
            continue

        user_msg = (
            base_context
            + f"\n\nClassify ONLY these {len(batch_names)} tables "
            f"(skip all others): {batch_names}"
        )

        assistant_content = _ClassificationList(classifications=batch_labels).model_dump_json()
        batched_records.append({
            "messages": [
                {"role": "system", "content": _AGENT3_SYSTEM},
                {"role": "user", "content": user_msg},
                {"role": "assistant", "content": assistant_content},
            ]
        })

    return batched_records


total_in = 0
total_out = 0

for jsonl_path in sorted(LABELED_DIR.glob("*.jsonl")):
    out_path = OUTPUT_DIR / jsonl_path.name
    out_records = []

    for line in jsonl_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        total_in += 1
        record = json.loads(line)
        batches = split_example(record)
        out_records.extend(batches)
        total_out += len(batches)

    out_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in out_records) + "\n",
        encoding="utf-8",
    )
    print(f"{jsonl_path.name}: {total_in} → {len(out_records)} examples")
    total_in = 0  # reset per file

print(f"\nTotal output examples: {total_out}")
print(f"Written to: {OUTPUT_DIR}/")
