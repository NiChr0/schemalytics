#!/usr/bin/env python3
"""
Validate all JSONL files in finetune/labeled/.

Run from repo root:
    python finetune/scripts/04_validate_dataset.py
"""

import json
import sys
from collections import Counter
from pathlib import Path

from pydantic import BaseModel, ValidationError

from schemalytics.models import TableClassificationResult

LABELED_DIR = Path("finetune/labeled")
VALID_ROLES = {"fact", "dimension", "bridge", "reference"}
VALID_CONFIDENCES = {1, 2, 3}


class _ClassificationList(BaseModel):
    classifications: list[TableClassificationResult]


def validate_file(path: Path) -> tuple[list[dict], list[str]]:
    """Return (valid_records, errors)."""
    records = []
    errors = []

    for line_num, raw in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        raw = raw.strip()
        if not raw:
            continue

        prefix = f"{path.name}:{line_num}"

        try:
            record = json.loads(raw)
        except json.JSONDecodeError as e:
            errors.append(f"{prefix}: invalid JSON — {e}")
            continue

        messages = record.get("messages", [])
        if len(messages) != 3 or [m["role"] for m in messages] != ["system", "user", "assistant"]:
            errors.append(f"{prefix}: messages must be [system, user, assistant]")
            continue

        assistant_content = messages[2]["content"]
        try:
            label_json = json.loads(assistant_content)
            validated = _ClassificationList.model_validate(label_json)
        except (json.JSONDecodeError, ValidationError) as e:
            errors.append(f"{prefix}: assistant content invalid — {e}")
            continue

        for c in validated.classifications:
            if c.role not in VALID_ROLES:
                errors.append(f"{prefix}: invalid role '{c.role}' for table '{c.table_name}'")
            if c.confidence not in VALID_CONFIDENCES:
                errors.append(f"{prefix}: invalid confidence {c.confidence} for table '{c.table_name}'")

        records.append({"path": str(path), "line": line_num, "classifications": validated.classifications})

    return records, errors


def main() -> None:
    jsonl_files = sorted(LABELED_DIR.glob("*.jsonl"))
    if not jsonl_files:
        print(f"No JSONL files found in {LABELED_DIR}/")
        sys.exit(0)

    all_records = []
    all_errors = []
    role_counter: Counter = Counter()

    for path in jsonl_files:
        records, errors = validate_file(path)
        all_records.extend(records)
        all_errors.extend(errors)
        for r in records:
            for c in r["classifications"]:
                role_counter[c.role] += 1

    total_tables = sum(len(r["classifications"]) for r in all_records)

    print(f"Files:         {len(jsonl_files)}")
    print(f"Examples:      {len(all_records)}")
    print(f"Total tables:  {total_tables}")
    if all_records:
        print(f"Avg per ex:    {total_tables / len(all_records):.1f}")
    print()
    print("Role distribution:")
    for role in ["fact", "dimension", "bridge", "reference"]:
        count = role_counter.get(role, 0)
        pct = count / total_tables * 100 if total_tables else 0
        print(f"  {role:<12} {count:>4}  ({pct:.1f}%)")
    print()

    if all_errors:
        print(f"ERRORS ({len(all_errors)}):")
        for e in all_errors:
            print(f"  {e}")
        sys.exit(1)
    else:
        print("All examples valid.")


if __name__ == "__main__":
    main()
