# Schemalytics Fine-Tune Pipeline

Fine-tune `Qwen2.5-Coder-7B-Instruct` on table classification examples to replace the base model
for Agent 3 (`classify_tables()` in `planner.py`). The resulting model is exported as GGUF and
served via Ollama with zero changes to the schemalytics source.

---

## Prerequisites

- macOS with Apple Silicon (M1/M2/M3)
- Docker Postgres running on `localhost:5432` (password: `mypassword`)
- schemalytics installed in your active venv
- `pip install mlx-lm` (for fine-tuning)
- `llama.cpp` installed (for GGUF export)
- Ollama installed

Start the test Postgres DB if needed:
```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=mypassword postgres:15
```

---

## Phase 1 — Collect Schema Data

### 1a. Download public schemas
```bash
bash finetune/scripts/download_schemas.sh
# Output: finetune/schemas/*.sql
```

### 1b. Load a schema and extract
```bash
bash finetune/scripts/01_load_schema.sh finetune/schemas/sakila.sql sakila
# Output: finetune/extracted/sakila.json
```

Repeat for each schema you downloaded.

---

## Phase 2 — Label with Claude.ai

### 2a. Generate the labeling prompt
```bash
python finetune/scripts/02_generate_prompt.py finetune/extracted/sakila.json
```

Copy the block between `=== PASTE INTO CLAUDE.AI ===` and `=== END PASTE ===` into Claude.ai.

### 2b. Save the label response
Copy Claude.ai's JSON response, then:
```bash
pbpaste | python finetune/scripts/03_save_label.py \
    --schema finetune/extracted/sakila.json \
    --output finetune/labeled/sakila.jsonl
```

Or pass inline:
```bash
python finetune/scripts/03_save_label.py \
    --schema finetune/extracted/sakila.json \
    --output finetune/labeled/sakila.jsonl \
    --label '{"classifications": [...]}'
```

Repeat for every schema in `finetune/extracted/`.

---

## Phase 3 — Validate and Build Dataset

### 3a. Validate all labeled examples
```bash
python finetune/scripts/04_validate_dataset.py
```

Fix any reported errors before proceeding.

### 3b. Build train/eval splits
```bash
python finetune/scripts/05_build_dataset.py
# Output: finetune/dataset/train.jsonl (85%)
#         finetune/dataset/eval.jsonl  (15%)
```

---

## Phase 4 — Fine-Tune

```bash
bash finetune/mlx/finetune.sh
# Logs: finetune/mlx/training.log
# Adapters: finetune/mlx/adapters/
```

Estimated time: 2–4 hours on M3 Air. Use a cooling pad and stay plugged in.

---

## Phase 5 — Export to Ollama

```bash
bash finetune/mlx/export.sh
```

This fuses the LoRA adapters, converts to GGUF (Q4_K_M), and imports into Ollama as
`schemalytics-agent3`.

Test the model:
```bash
ollama run schemalytics-agent3
```

---

## Phase 6 — Evaluate

```bash
python finetune/scripts/06_eval.py \
    --eval-set finetune/dataset/eval.jsonl \
    --base-model qwen2.5-coder:7b \
    --finetuned-model schemalytics-agent3
```

---

## Using the Fine-Tuned Model

```bash
SCHEMALYTICS_OLLAMA_MODEL=schemalytics-agent3 schemalytics generate -c postgresql://... -o ./out
```

No other changes needed — the pipeline uses the model for all agents by default, and Agent 3
will benefit most from the specialised fine-tune.

---

## Directory Layout

```
finetune/
├── schemas/        # Downloaded SQL dumps (gitignored content)
├── extracted/      # schema.json per DB (gitignored content)
├── labeled/        # Claude.ai-labeled JSONL per schema (gitignored content)
├── dataset/
│   ├── train.jsonl
│   └── eval.jsonl
├── scripts/
│   ├── download_schemas.sh
│   ├── 01_load_schema.sh
│   ├── 02_generate_prompt.py
│   ├── 03_save_label.py
│   ├── 04_validate_dataset.py
│   ├── 05_build_dataset.py
│   └── 06_eval.py
└── mlx/
    ├── config.yaml
    ├── finetune.sh
    └── export.sh
```
