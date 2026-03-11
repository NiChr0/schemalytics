#!/bin/bash
# Fuse LoRA adapters into base model and export to GGUF for Ollama
# Prerequisites: pip install mlx-lm, llama.cpp must be installed
# Run from repo root: bash finetune/mlx/export.sh

set -e

ADAPTER_PATH="finetune/mlx/adapters"
FUSED_PATH="finetune/mlx/fused_model"
GGUF_PATH="finetune/mlx/schemalytics-agent3.gguf"

echo "Step 1: Fuse adapters into base model..."
mlx_lm.fuse \
  --model mlx-community/Qwen2.5-Coder-7B-Instruct-4bit \
  --adapter-path "$ADAPTER_PATH" \
  --save-path "$FUSED_PATH"

echo "Step 2: Convert fused model to GGUF (Q4_K_M)..."
python -m llama_cpp.convert_hf_to_gguf \
  "$FUSED_PATH" \
  --outfile "$GGUF_PATH" \
  --outtype q4_k_m

echo "Step 3: Create Ollama Modelfile..."
cat > finetune/mlx/Modelfile << EOF
FROM $GGUF_PATH
PARAMETER temperature 0
PARAMETER num_ctx 12288
PARAMETER num_predict 2048
EOF

echo "Step 4: Import into Ollama..."
ollama create schemalytics-agent3 -f finetune/mlx/Modelfile

echo "Done. Test with:"
echo "  ollama run schemalytics-agent3"
echo ""
echo "To use in Schemalytics, set env var:"
echo "  SCHEMALYTICS_OLLAMA_MODEL=schemalytics-agent3"
