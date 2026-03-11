#!/usr/bin/env python3
"""
Merge labeled JSONL files into train/eval splits.

Run from repo root:
    python finetune/scripts/05_build_dataset.py
"""

import json
import random
from pathlib import Path

LABELED_DIR = Path("finetune/labeled_batched")
DATASET_DIR = Path("finetune/dataset")
TRAIN_PATH = DATASET_DIR / "train.jsonl"
EVAL_PATH = DATASET_DIR / "eval.jsonl"
SEED = 42
EVAL_FRACTION = 0.15


def main() -> None:
    jsonl_files = sorted(LABELED_DIR.glob("*.jsonl"))
    if not jsonl_files:
        print(f"No JSONL files found in {LABELED_DIR}/")
        return

    records = []
    for path in jsonl_files:
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line:
                records.append(json.loads(line))

    if not records:
        print("No records found.")
        return

    random.seed(SEED)
    random.shuffle(records)

    n_eval = max(1, int(len(records) * EVAL_FRACTION))
    eval_records = records[:n_eval]
    train_records = records[n_eval:]

    DATASET_DIR.mkdir(parents=True, exist_ok=True)

    TRAIN_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in train_records) + "\n",
        encoding="utf-8",
    )
    EVAL_PATH.write_text(
        "\n".join(json.dumps(r, ensure_ascii=False) for r in eval_records) + "\n",
        encoding="utf-8",
    )

    print(f"Total examples: {len(records)}")
    print(f"Train:          {len(train_records)} → {TRAIN_PATH}")
    print(f"Eval:           {len(eval_records)} → {EVAL_PATH}")


if __name__ == "__main__":
    main()
