#!/bin/bash
# Fine-tune Qwen2.5-Coder-7B-Instruct with LoRA via MLX-LM
# Prerequisites: pip install mlx-lm
# Run from repo root: bash finetune/mlx/finetune.sh

set -e

echo "Starting fine-tune — estimated time: 2-4 hours on M3 Air"
echo "Tip: use a cooling pad and plug in power"

mlx_lm.lora \
  --config finetune/mlx/config.yaml \
  --train \
  2>&1 | tee finetune/mlx/training.log

echo "Done. Adapters saved to finetune/mlx/adapters/"
