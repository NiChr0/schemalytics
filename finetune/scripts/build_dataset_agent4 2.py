#!/usr/bin/env python3
"""
Merge Agent 4a (Silver) and Agent 4b (Gold) labeled JSONL files into
separate train/eval splits — one pair per agent.

Run from repo root:
    python finetune/scripts/build_dataset_agent4.py

Outputs:
    finetune/dataset/silver_train.jsonl   (85%)
    finetune/dataset/silver_eval.jsonl    (15%)
    finetune/dataset/gold_train.jsonl     (85%)
    finetune/dataset/gold_eval.jsonl      (15%)
"""

import json
import random
from pathlib import Path

SILVER_DIR = Path("finetune/labeled_silver")
GOLD_DIR = Path("finetune/labeled_gold")
DATASET_DIR = Path("finetune/dataset")
SEED = 42
EVAL_FRACTION = 0.15

# No MAX_CHARS filter — 3090 24GB with max_seq_length=8192 handles all schema sizes.


def load_records(directory: Path) -> list[dict]:
    """Load all JSONL records from a directory, stripping _meta."""
    records = []
    for path in sorted(directory.glob("*.jsonl")):
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            record = json.loads(line)
            record.pop("_meta", None)
            records.append(record)
    return records


def split_and_save(
    records: list[dict],
    train_path: Path,
    eval_path: Path,
    label: str,
) -> None:
    if not records:
        print(f"  {label}: no records found — skipping")
        return

    random.seed(SEED)
    random.shuffle(records)

    n_eval = max(1, int(len(records) * EVAL_FRACTION))
    eval_records = records[:n_eval]
    train_records = records[n_eval:]

    train_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train_records) + "\n",
        encoding="utf-8",
    )
    eval_path.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in eval_records) + "\n",
        encoding="utf-8",
    )
    print(f"  {label}: {len(records)} total  ->  {len(train_records)} train / {len(eval_records)} eval")


def main() -> None:
    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    silver_records = load_records(SILVER_DIR)
    gold_records = load_records(GOLD_DIR)

    print(f"Building Agent 4a (Silver) dataset from {SILVER_DIR}/")
    split_and_save(
        silver_records,
        DATASET_DIR / "silver_train.jsonl",
        DATASET_DIR / "silver_eval.jsonl",
        label="Silver (4a)",
    )

    print(f"Building Agent 4b (Gold) dataset from {GOLD_DIR}/")
    split_and_save(
        gold_records,
        DATASET_DIR / "gold_train.jsonl",
        DATASET_DIR / "gold_eval.jsonl",
        label="Gold  (4b)",
    )


if __name__ == "__main__":
    main()
