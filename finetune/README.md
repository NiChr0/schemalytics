# Schemalytics Fine-Tune Pipeline

Fine-tune `unsloth/Qwen3.5-4B` on table classification examples to replace the base model
for Agent 3 (`classify_tables()` in `planner.py`). The resulting model is exported as GGUF and
served via Ollama as `schemalytics-classification-agent` — zero changes to the schemalytics source.

---

## Pre-trained Model (Recommended)

The fine-tuned model is available on Ollama Hub. You do not need to run this pipeline unless
you want to re-train or extend it:

```bash
ollama pull nichr0/schemalytics-classification-agent
```

Then use it:
```bash
SCHEMALYTICS_OLLAMA_MODEL=schemalytics-classification-agent \
schemalytics generate -c postgresql://... -o ./out
```

---

## Model Details

| Property | Value |
|----------|-------|
| Base model | `unsloth/Qwen3.5-4B` |
| Method | QLoRA (r=8, lora_alpha=16) |
| Hardware | NVIDIA RTX 3060 Ti 8 GB (CUDA, Ampere, bf16) |
| Framework | Unsloth + TRL SFTTrainer |
| Steps | 400 (cosine LR, lr=3e-5) |
| Training examples | 327 |
| Eval examples | 57 |
| Train loss | 0.055 |
| Eval loss | 0.058 (no overfitting) |
| Export format | GGUF Q4\_K\_M (2.6 GB) |
| Ollama model | `schemalytics-classification-agent` |

**Training data sources:**
- Classic benchmarks: Northwind, Sakila, Chinook, AdventureWorks, Pagila, and others
- Complex production schemas: GLPI (441 tables), OpenEMR (282), PrestaShop (242), OpenCart (136), Icinga (66), Roundcube, TYPO3

---

## Prerequisites (to retrain)

**NVIDIA GPU (RTX 30xx / 40xx, 8 GB+ VRAM, Windows/Linux):**
```bash
pip install -r finetune/cuda/requirements.txt
```

**Both platforms:**
- `ANTHROPIC_API_KEY` set in your environment (used for automated labeling)
- Ollama installed
- `llama.cpp` built with CUDA support (for GGUF export — see Phase 5)

---

## Phase 1 — Collect Schema Data

### 1a. Download public SQL schemas (classic benchmarks)
```bash
bash finetune/scripts/download_schemas.sh
# Output: finetune/schemas/*.sql
```

### 1b. Extract schemas to JSON
```bash
bash finetune/scripts/01_load_schema.sh finetune/schemas/sakila.sql sakila
# Output: finetune/extracted/sakila.json
```

Repeat for each schema. Extracted JSON files go in `finetune/extracted/`.

### 1c. Download complex real-world schemas (optional but recommended)
```bash
python finetune/scripts/download_and_extract_complex.py
# Output: finetune/extracted_complex/*.json
# Includes: GLPI, OpenEMR, PrestaShop, OpenCart, Icinga, TYPO3, Roundcube, Northwind
```

---

## Phase 2 — Auto-Label with Claude

### 2a. Label classic Spider/benchmark schemas
```bash
python finetune/scripts/label_spider.py
# Output: finetune/labeled_spider/*.jsonl
# Requires: ANTHROPIC_API_KEY
```

### 2b. Label complex real-world schemas
```bash
python finetune/scripts/label_complex.py
# Output: finetune/labeled_complex/*.jsonl
# Uses CHUNK_SIZE=30 for large schemas (300+ tables)
```

Both scripts are resumable — already-labeled files are skipped automatically.

---

## Phase 3 — Build Dataset

### 3a. Merge and split into train/eval
```bash
python finetune/scripts/05_build_dataset.py
# Output: finetune/dataset/train.jsonl (85%)
#         finetune/dataset/eval.jsonl  (15%)
```

---

## Phase 4 — Fine-Tune (NVIDIA GPU)

```bash
# Run from repo root
python finetune/cuda/finetune.py
# Adapters saved to: finetune/cuda/adapters-qwen3.5-4b-v5/
```

Estimated time: 30–60 minutes on RTX 3060 Ti. Monitor train and eval loss — they should track
together across all epochs. If eval loss diverges upward, the dataset is too small or too repetitive.

---

## Phase 5 — Export to GGUF + Ollama

The export is a 3-step manual process (Unsloth's built-in GGUF export requires network access
to download the conversion script; the manual path is more reliable):

**Step 1 — Merge LoRA adapters into full HF model:**
```python
from unsloth import FastLanguageModel
model, tokenizer = FastLanguageModel.from_pretrained(
    "finetune/cuda/adapters-qwen3.5-4b-v5/checkpoint-400",
    max_seq_length=1024, load_in_4bit=True,
)
model.save_pretrained_merged("finetune/cuda/merged-qwen3.5-4b", tokenizer, save_method="merged_16bit")
```

**Step 2 — Convert to GGUF F16:**
```bash
python llama.cpp/convert_hf_to_gguf.py finetune/cuda/merged-qwen3.5-4b \
  --outfile finetune/cuda/schemalytics-v6-f16.gguf \
  --outtype f16
```

**Step 3 — Quantize to Q4\_K\_M:**
```bash
llama.cpp/build/bin/llama-quantize \
  finetune/cuda/schemalytics-v6-f16.gguf \
  finetune/cuda/schemalytics-v6-Q4_K_M.gguf \
  Q4_K_M
```

**Step 4 — Import into Ollama:**
```bash
# Create Modelfile
cat > finetune/cuda/Modelfile-classification-agent << 'EOF'
FROM /absolute/path/to/schemalytics-v6-Q4_K_M.gguf
PARAMETER temperature 0
PARAMETER num_ctx 12288
PARAMETER num_predict 2048
EOF

ollama create schemalytics-classification-agent -f finetune/cuda/Modelfile-classification-agent
```

Test the model:
```bash
ollama run schemalytics-classification-agent
```

---

## Phase 6 — Evaluate

```bash
python finetune/scripts/06_eval.py \
    --eval-set finetune/dataset/eval.jsonl \
    --base-model qwen3-30b-data \
    --finetuned-model schemalytics-classification-agent
```

---

## Using the Fine-Tuned Model

```bash
SCHEMALYTICS_OLLAMA_MODEL=schemalytics-classification-agent \
schemalytics generate -c postgresql://... -o ./out
```

No other changes needed — the pipeline uses this model only for Agent 3 table classification.

---

## Directory Layout

```
finetune/
├── schemas/                # Downloaded SQL dumps
├── extracted/              # Extracted JSON (classic schemas)
├── extracted_complex/      # Extracted JSON (complex production schemas)
├── extracted_spider/       # Extracted JSON (Spider benchmark)
├── labeled_spider/         # Auto-labeled JSONL (classic/Spider)
├── labeled_complex/        # Auto-labeled JSONL (complex schemas)
├── labeled_batched/        # Batched JSONL used for dataset build
├── dataset/
│   ├── train.jsonl         # 327 training examples
│   └── eval.jsonl          # 57 eval examples
├── scripts/
│   ├── download_schemas.sh
│   ├── download_and_extract_complex.py
│   ├── 01_load_schema.sh
│   ├── label_spider.py         # Auto-label via Anthropic API
│   ├── label_complex.py        # Auto-label complex schemas (chunked)
│   ├── 04_validate_dataset.py
│   ├── 05_build_dataset.py
│   └── 06_eval.py
├── mlx/                    # Apple Silicon training (MLX-LM) — legacy
│   ├── config.yaml
│   ├── finetune.sh
│   └── export.sh
└── cuda/                   # NVIDIA GPU training (Unsloth + QLoRA) — primary
    ├── finetune.py             # train + optional export
    ├── requirements.txt
    └── Modelfile-qwen3.5-4b-v6
```
