#!/usr/bin/env python3
"""
Evaluate base model vs fine-tuned model on the held-out eval set.

Run from repo root:
    python finetune/scripts/06_eval.py \\
        --eval-set finetune/dataset/eval.jsonl \\
        --base-model qwen2.5-coder:7b \\
        --finetuned-model schemalytics-agent3
"""

import argparse
import json
import os
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic import BaseModel

from schemalytics.models import TableClassificationResult
from schemalytics import llm as llm_module

VALID_ROLES = ["fact", "dimension", "bridge", "reference"]


class _ClassificationList(BaseModel):
    classifications: list[TableClassificationResult]


def load_eval_set(path: Path) -> list[dict]:
    records = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            records.append(json.loads(line))
    return records


def predict(system: str, user: str, model_name: str) -> list[TableClassificationResult]:
    """Run inference with a specific Ollama model, return classifications."""
    original_model = os.environ.get("SCHEMALYTICS_OLLAMA_MODEL")
    os.environ["SCHEMALYTICS_LLM_PROVIDER"] = "ollama"
    os.environ["SCHEMALYTICS_OLLAMA_MODEL"] = model_name

    # Reset the singleton so the new model name is picked up
    llm_module._ollama_client = None

    try:
        result = llm_module.query_structured(
            system=system,
            user=user,
            response_model=_ClassificationList,
            max_tokens=3256,
        )
        return result.classifications
    except Exception as e:
        print(f"  WARNING: inference failed for model {model_name}: {e}")
        return []
    finally:
        # Restore original env
        if original_model is not None:
            os.environ["SCHEMALYTICS_OLLAMA_MODEL"] = original_model
        elif "SCHEMALYTICS_OLLAMA_MODEL" in os.environ:
            del os.environ["SCHEMALYTICS_OLLAMA_MODEL"]
        llm_module._ollama_client = None


def compute_metrics(
    predictions: list[list[TableClassificationResult]],
    ground_truths: list[list[TableClassificationResult]],
) -> dict[str, Any]:
    correct = 0
    total = 0
    tp: dict[str, int] = defaultdict(int)
    fp: dict[str, int] = defaultdict(int)
    fn: dict[str, int] = defaultdict(int)

    for pred_list, gt_list in zip(predictions, ground_truths):
        gt_map = {c.table_name: c.role for c in gt_list}
        pred_map = {c.table_name: c.role for c in pred_list}

        for table_name, gt_role in gt_map.items():
            total += 1
            pred_role = pred_map.get(table_name)
            if pred_role == gt_role:
                correct += 1
                tp[gt_role] += 1
            else:
                fn[gt_role] += 1
                if pred_role:
                    fp[pred_role] += 1

    accuracy = correct / total if total else 0.0

    f1_scores: dict[str, float] = {}
    for role in VALID_ROLES:
        precision = tp[role] / (tp[role] + fp[role]) if (tp[role] + fp[role]) else 0.0
        recall = tp[role] / (tp[role] + fn[role]) if (tp[role] + fn[role]) else 0.0
        f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
        f1_scores[role] = f1

    return {"accuracy": accuracy, "f1": f1_scores, "total": total, "correct": correct}


def main() -> None:
    parser = argparse.ArgumentParser(description="Evaluate base vs fine-tuned model on eval set.")
    parser.add_argument("--eval-set", required=True, help="Path to eval.jsonl")
    parser.add_argument("--base-model", required=True, help="Ollama model name for base model")
    parser.add_argument("--finetuned-model", required=True, help="Ollama model name for fine-tuned model")
    args = parser.parse_args()

    eval_path = Path(args.eval_set)
    if not eval_path.exists():
        print(f"ERROR: Eval set not found: {eval_path}")
        return

    records = load_eval_set(eval_path)
    print(f"Loaded {len(records)} eval examples")

    ground_truths: list[list[TableClassificationResult]] = []
    systems: list[str] = []
    users: list[str] = []

    for r in records:
        messages = r["messages"]
        systems.append(messages[0]["content"])
        users.append(messages[1]["content"])
        gt_json = json.loads(messages[2]["content"])
        ground_truths.append(_ClassificationList.model_validate(gt_json).classifications)

    for model_name, label in [(args.base_model, "base"), (args.finetuned_model, "finetuned")]:
        print(f"\nRunning {label} model ({model_name}) on {len(records)} examples...")
        predictions = []
        for i, (sys_msg, usr_msg) in enumerate(zip(systems, users), start=1):
            print(f"  Example {i}/{len(records)}", end="\r")
            preds = predict(sys_msg, usr_msg, model_name)
            predictions.append(preds)
        print()

        metrics = compute_metrics(predictions, ground_truths)
        results = [(label, model_name, metrics)]

    # Collect both sets of results then print comparison
    all_results = []
    for model_name, label in [(args.base_model, "base"), (args.finetuned_model, "finetuned")]:
        print(f"\nRunning {label} model ({model_name})...")
        predictions = []
        for i, (sys_msg, usr_msg) in enumerate(zip(systems, users), start=1):
            print(f"  Example {i}/{len(records)}", end="\r")
            preds = predict(sys_msg, usr_msg, model_name)
            predictions.append(preds)
        print()
        metrics = compute_metrics(predictions, ground_truths)
        all_results.append((label, model_name, metrics))

    # Print comparison table
    print()
    header = f"{'Model':<30} {'Accuracy':>9} {'Fact F1':>9} {'Dim F1':>8} {'Bridge F1':>10} {'Ref F1':>8}"
    print(header)
    print("-" * len(header))
    for label, model_name, m in all_results:
        display = f"{model_name} ({label})"
        row = (
            f"{display:<30}"
            f" {m['accuracy']:>9.2f}"
            f" {m['f1']['fact']:>9.2f}"
            f" {m['f1']['dimension']:>8.2f}"
            f" {m['f1']['bridge']:>10.2f}"
            f" {m['f1']['reference']:>8.2f}"
        )
        print(row)


if __name__ == "__main__":
    main()
