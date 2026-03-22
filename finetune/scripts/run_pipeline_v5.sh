#!/usr/bin/env bash
# Full pipeline: download complex schemas -> label -> rebuild dataset -> train v5
# Run from repo root. Requires ANTHROPIC_API_KEY to be set.
set -e

PYTHON="finetune/cuda/.venv/Scripts/python.exe"

echo "=== Step 1: Download and extract complex schemas ==="
PYTHONUTF8=1 $PYTHON finetune/scripts/download_and_extract_complex.py

echo ""
echo "=== Step 2: Label complex schemas with Claude API ==="
PYTHONUTF8=1 $PYTHON finetune/scripts/label_complex.py

echo ""
echo "=== Step 3: Copy all labels to labeled_batched ==="
cp finetune/labeled_complex/*.jsonl finetune/labeled_batched/ 2>/dev/null || true
echo "labeled_batched now has $(ls finetune/labeled_batched/ | wc -l) files"

echo ""
echo "=== Step 4: Rebuild train/eval dataset ==="
PYTHONUTF8=1 $PYTHON finetune/scripts/05_build_dataset.py

echo ""
echo "=== Step 5: Train v5 ==="
PYTHONUTF8=1 $PYTHON finetune/cuda/finetune.py > finetune/cuda/train-qwen3.5-4b-v5.log 2>&1

echo ""
echo "=== Pipeline complete ==="
