#!/bin/bash
# =============================================================================
# Schemalytics — vast.ai RTX 3090 setup + training script
#
# Usage (run from repo root after cloning / rsyncing):
#   bash finetune/cuda/setup_vastai.sh [silver|gold|both]
#
# Default: both (silver first, then gold)
#
# Prereqs on the vast.ai instance:
#   - PyTorch image with CUDA 12.x (e.g. pytorch/pytorch:2.3.0-cuda12.1-cudnn8-runtime)
#   - git + python3 available (they always are on vast.ai base images)
# =============================================================================

set -euo pipefail

TARGET="${1:-both}"

echo "============================================================"
echo " Schemalytics fine-tune — vast.ai setup"
echo " Target : $TARGET"
echo " $(date)"
echo "============================================================"

# ---------------------------------------------------------------------------
# 1. Install dependencies
# ---------------------------------------------------------------------------
echo ""
echo "[1/4] Installing Python dependencies..."

# PyTorch is pre-installed in the vast.ai pytorch image — skip to avoid
# version conflicts. Install unsloth first so it can pin compatible versions.
pip install --quiet "unsloth[colab-new] @ git+https://github.com/unslothai/unsloth.git"

# Install remaining training deps
pip install --quiet \
    "trl>=0.12.0" \
    "datasets>=2.18.0" \
    "transformers>=4.45.0" \
    "accelerate>=0.34.0" \
    "bitsandbytes>=0.43.0" \
    "peft>=0.12.0"

echo "Dependencies installed."

# ---------------------------------------------------------------------------
# 2. Verify GPU
# ---------------------------------------------------------------------------
echo ""
echo "[2/4] GPU check..."
python - <<'EOF'
import torch
assert torch.cuda.is_available(), "CUDA not available — check your instance type!"
gpu = torch.cuda.get_device_name(0)
mem_gb = torch.cuda.get_device_properties(0).total_memory / 1e9
print(f"  GPU  : {gpu}")
print(f"  VRAM : {mem_gb:.1f} GB")
if mem_gb < 20:
    print("  WARNING: less than 20 GB VRAM — batch_size=4 may OOM, consider reducing.")
EOF

# ---------------------------------------------------------------------------
# 3. Verify dataset files exist
# ---------------------------------------------------------------------------
echo ""
echo "[3/4] Checking dataset files..."
for f in \
    finetune/dataset/silver_train.jsonl \
    finetune/dataset/silver_eval.jsonl \
    finetune/dataset/gold_train.jsonl \
    finetune/dataset/gold_eval.jsonl
do
    if [[ ! -f "$f" ]]; then
        echo "  MISSING: $f"
        echo "  Run finetune/scripts/05_build_dataset.py locally first, then rsync the dataset."
        exit 1
    fi
    lines=$(wc -l < "$f")
    echo "  OK: $f  ($lines lines)"
done

# ---------------------------------------------------------------------------
# 4. Run training
# ---------------------------------------------------------------------------
echo ""
echo "[4/4] Starting training..."

run_silver() {
    echo ""
    echo "--- Silver (Agent 4a) ---"
    python finetune/cuda/finetune_silver.py 2>&1 | tee finetune/cuda/training_silver.log
    echo "Silver training complete. Adapters: finetune/cuda/adapters-silver-v2/"
}

run_gold() {
    echo ""
    echo "--- Gold (Agent 4b) ---"
    python finetune/cuda/finetune_gold.py 2>&1 | tee finetune/cuda/training_gold.log
    echo "Gold training complete. Adapters: finetune/cuda/adapters-gold-v2/"
}

case "$TARGET" in
    silver) run_silver ;;
    gold)   run_gold ;;
    both)   run_silver; run_gold ;;
    *)
        echo "Unknown target '$TARGET'. Use: silver | gold | both"
        exit 1
        ;;
esac

echo ""
echo "============================================================"
echo " All done. $(date)"
echo ""
echo " Adapter locations:"
echo "   Silver : finetune/cuda/adapters-silver-v2/"
echo "   Gold   : finetune/cuda/adapters-gold-v2/"
echo ""
echo " To download adapters back to your Mac:"
echo "   rsync -avz root@<instance-ip>:/root/schemalytics/finetune/cuda/adapters-silver-v2 finetune/cuda/"
echo "   rsync -avz root@<instance-ip>:/root/schemalytics/finetune/cuda/adapters-gold-v2  finetune/cuda/"
echo ""
echo " To export to GGUF after downloading, run locally:"
echo "   python finetune/cuda/finetune_silver.py --export-only"
echo "   python finetune/cuda/finetune_gold.py   --export-only"
echo "============================================================"
