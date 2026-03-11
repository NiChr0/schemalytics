# Fine-Tune Plan: Schemalytics Agent 3 — Table Classification
> Hand this file to Claude Code in VSCode. Read the full plan before writing any code.

---

## Goal

Fine-tune `Qwen2.5-Coder-7B-Instruct` on table classification examples to replace the current
base model for Agent 3 (`classify_tables()` in `planner.py`). The fine-tuned model will be
exported as GGUF, served via Ollama, and swapped in via the existing `SCHEMALYTICS_LLM_PROVIDER`
/ model config with zero pipeline changes.

---

## Repo Context (read before touching anything)

- Agent 3 lives in `schemalytics/planner.py` → `classify_tables()`
- System prompt: `_AGENT3_SYSTEM` constant in `planner.py`
- Input: compact schema summary + FK heuristics + business context
- Output: `list[TableClassificationResult]` via `_ClassificationList` wrapper
- Pydantic model in `schemalytics/models.py`:

```python
class TableClassificationResult(BaseModel):
    table_name: str
    role: str  # "fact", "dimension", "bridge", "reference"
    confidence: int  # 1, 2, or 3
    reasoning: str
    needs_clarification: bool
```

- The LLM never sees raw schema JSON — it sees the output of `_compact_schema_summary(schema)`
  and `_heuristic_summary(heuristics)`. Read those functions carefully before building prompts.

---

## Directory Structure to Create

Create this under the repo root — do NOT mix with `schemalytics/` source:

```
finetune/
├── README.md                  # How to run the full pipeline
├── schemas/                   # Raw SQL dump files downloaded from internet
│   └── .gitkeep
├── extracted/                 # schema.json output per DB (from schemalytics extract)
│   └── .gitkeep
├── labeled/                   # Claude.ai-labeled JSONL per schema
│   └── .gitkeep
├── dataset/
│   ├── train.jsonl            # Final training set (merged, validated)
│   └── eval.jsonl             # Held-out eval set (10-20% split)
├── scripts/
│   ├── 01_load_schema.sh      # Load a SQL dump into Docker Postgres + run extract
│   ├── 02_generate_prompt.py  # Given schema JSON → print Claude.ai labeling prompt
│   ├── 03_save_label.py       # Given Claude.ai JSON response → save as JSONL example
│   ├── 04_validate_dataset.py # Validate all JSONL, check roles, confidence ranges
│   ├── 05_build_dataset.py    # Merge labeled/ → train.jsonl + eval.jsonl
│   └── 06_eval.py             # Run fine-tuned model vs base model on eval set
└── mlx/
    ├── finetune.sh            # MLX-LM fine-tune command
    ├── config.yaml            # LoRA hyperparameters
    └── export.sh              # Convert MLX adapter → GGUF → Ollama import
```

---

## Phase 1 — Schema Collection

### Task
Build `scripts/01_load_schema.sh` — a script that:
1. Accepts a SQL dump file path and a DB name as arguments
2. Creates a fresh DB in the running Docker Postgres container (`northwind-test`, port 5432,
   password `mypassword`)
3. Loads the SQL dump
4. Runs `schemalytics extract` and saves output to `finetune/extracted/<dbname>.json`

```bash
# Usage:
bash finetune/scripts/01_load_schema.sh ./finetune/schemas/sakila.sql sakila
# Output: finetune/extracted/sakila.json
```

### Target Public Schemas to Download
Download these SQL dumps into `finetune/schemas/`. All are public domain or MIT licensed.
Write a `download_schemas.sh` helper that fetches them automatically:

| DB Name | URL | Domain |
|---------|-----|--------|
| sakila | https://raw.githubusercontent.com/jOOQ/sakila/main/postgres-sakila-db/postgres-sakila-schema.sql | Video rental |
| employees | https://raw.githubusercontent.com/vrajmohan/pgsql-sample-db/master/employee/employee.sql | HR |
| pagila | https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-schema.sql | DVD rental |
| hospital | https://raw.githubusercontent.com/rohitraut3366/hospital-management-system-database/master/hospital.sql | Healthcare |
| ecommerce | https://raw.githubusercontent.com/paulius-mongirdas/ecommerce-database/main/database.sql | E-commerce |
| university | https://raw.githubusercontent.com/YohanObadia/SQL-exercises/master/university_db.sql | Education |

If any URL fails (404), skip it and note it. Do not block the script.

Add more schemas from GitHub search: `filename:schema.sql language:sql` — target 20 total,
covering diverse industries: logistics, fintech, healthcare, SaaS, manufacturing, hospitality.

---

## Phase 2 — Labeling Prompt Generator

### Task
Build `scripts/02_generate_prompt.py`:

```bash
python finetune/scripts/02_generate_prompt.py finetune/extracted/sakila.json
```

This script must:

1. Load the schema JSON using `schemalytics`'s own models:
```python
from schemalytics.models import Schema
schema = Schema.model_validate_json(Path(path).read_text())
```

2. Run the same FK heuristics used in production:
```python
from schemalytics.planner import classify_by_fk_graph, _compact_schema_summary, _heuristic_summary
```

3. Print a fully-formed prompt to stdout in this exact format — ready to paste into Claude.ai:

```
=== PASTE INTO CLAUDE.AI ===

You are a senior data engineer expert in Kimball dimensional modeling.

Classify each table in this database schema as one of:
- "fact": transactional/event table (measures + FK keys to dimensions)
- "dimension": descriptive entity table (attributes, looked up by facts)
- "bridge": resolves many-to-many between facts and dimensions
- "reference": small lookup/code table (status codes, types, categories)

For each table output:
- table_name: exact table name
- role: one of fact/dimension/bridge/reference
- confidence: 1 (uncertain), 2 (moderate), 3 (certain)
- reasoning: one sentence explaining why
- needs_clarification: true only if ambiguous without business context

Schema:
<compact schema summary output>

FK heuristic pre-classifications:
<heuristic summary output>

Respond ONLY with valid JSON in this exact structure — no preamble, no markdown:
{
  "classifications": [
    {
      "table_name": "orders",
      "role": "fact",
      "confidence": 3,
      "reasoning": "Has FK keys to customers and products, contains order_date and amount measures.",
      "needs_clarification": false
    }
  ]
}

=== END PASTE ===
```

4. Also print the schema name and table count as a header so you know what you're labeling.

---

## Phase 3 — Save Labels as JSONL

### Task
Build `scripts/03_save_label.py`:

```bash
python finetune/scripts/03_save_label.py \
  --schema finetune/extracted/sakila.json \
  --label '{"classifications": [...]}' \
  --output finetune/labeled/sakila.jsonl
```

Or accept label from stdin:
```bash
pbpaste | python finetune/scripts/03_save_label.py \
  --schema finetune/extracted/sakila.json \
  --output finetune/labeled/sakila.jsonl
```

This script must produce one JSONL line per table in this exact format (MLX-LM chat format):

```json
{
  "messages": [
    {
      "role": "system",
      "content": "<_AGENT3_SYSTEM prompt — read directly from planner.py, do not hardcode>"
    },
    {
      "role": "user",
      "content": "<same user message format that classify_tables() sends to the LLM>"
    },
    {
      "role": "assistant",
      "content": "{\"classifications\": [{\"table_name\": \"...\", \"role\": \"...\", ...}]}"
    }
  ]
}
```

**Critical:** The system and user message content must be byte-for-byte identical to what
`classify_tables()` sends in production. Import and call `_compact_schema_summary`,
`_heuristic_summary`, and read `_AGENT3_SYSTEM` directly from `schemalytics/planner.py`.
Do not duplicate or paraphrase them.

Validate the label JSON against `_ClassificationList` Pydantic model before saving.
Reject and print an error if validation fails.

---

## Phase 4 — Dataset Validation and Build

### Task
Build `scripts/04_validate_dataset.py`:
- Load all JSONL files from `finetune/labeled/`
- Validate each line parses as valid JSON with correct message structure
- Validate assistant content parses as `_ClassificationList`
- Check all roles are in `{"fact", "dimension", "bridge", "reference"}`
- Check confidence values are in `{1, 2, 3}`
- Print summary: total examples, tables per example, role distribution, any errors

Build `scripts/05_build_dataset.py`:
- Merge all validated JSONL from `finetune/labeled/`
- Shuffle with fixed seed (42)
- Split 85% train / 15% eval
- Write to `finetune/dataset/train.jsonl` and `finetune/dataset/eval.jsonl`
- Print final counts

---

## Phase 5 — MLX-LM Fine-Tune

### Task
Create `finetune/mlx/config.yaml`:

```yaml
# LoRA config for Qwen2.5-Coder-7B-Instruct on M3 24GB
model: "mlx-community/Qwen2.5-Coder-7B-Instruct-4bit"
train: true
data: "finetune/dataset"
seed: 42

# LoRA settings — conservative for 24GB Air (avoids OOM + thermals)
lora_layers: 8
lora_rank: 8
lora_alpha: 16
lora_dropout: 0.05

# Training
batch_size: 2
iters: 600
val_batches: 25
learning_rate: 2e-5
lr_schedule: cosine_decay
warmup: 50
grad_checkpoint: true   # critical for memory

# Logging
steps_per_report: 10
steps_per_eval: 100
save_every: 200
adapter_path: "finetune/mlx/adapters"
```

Create `finetune/mlx/finetune.sh`:

```bash
#!/bin/bash
# Fine-tune Qwen2.5-Coder-7B-Instruct with LoRA via MLX-LM
# Prerequisites: pip install mlx-lm

set -e

echo "Starting fine-tune — estimated time: 2-4 hours on M3 Air"
echo "Tip: use a cooling pad and plug in power"

mlx_lm.lora \
  --config finetune/mlx/config.yaml \
  --train \
  2>&1 | tee finetune/mlx/training.log

echo "Done. Adapters saved to finetune/mlx/adapters/"
```

Create `finetune/mlx/export.sh`:

```bash
#!/bin/bash
# Fuse LoRA adapters into base model and export to GGUF for Ollama
# Prerequisites: pip install mlx-lm, llama.cpp must be installed

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
```

---

## Phase 6 — Evaluation

### Task
Build `scripts/06_eval.py`:

```bash
python finetune/scripts/06_eval.py \
  --eval-set finetune/dataset/eval.jsonl \
  --base-model gemma3-data \
  --finetuned-model schemalytics-agent3
```

For each example in eval set:
1. Send the same system + user prompt to both models via `llm.query_structured()`
2. Compare predicted roles vs ground truth labels
3. Compute per-model: accuracy, per-role F1, confidence calibration
4. Print a side-by-side comparison table

Output format:
```
Model                  Accuracy   Fact F1   Dim F1   Bridge F1   Ref F1
gemma3-data (base)     0.71       0.68      0.74     0.52        0.61
schemalytics-agent3    0.89       0.91      0.88     0.79        0.84
```

---

## Implementation Order

Do these phases in order. Do not skip ahead.

1. `scripts/download_schemas.sh` + `scripts/01_load_schema.sh`
2. `scripts/02_generate_prompt.py`
3. `scripts/03_save_label.py`
4. `scripts/04_validate_dataset.py` + `scripts/05_build_dataset.py`
5. `finetune/mlx/config.yaml` + `finetune/mlx/finetune.sh` + `finetune/mlx/export.sh`
6. `scripts/06_eval.py`

---

## Hard Rules

- Never modify `schemalytics/` source code — this is a standalone `finetune/` module
- Always import from `schemalytics` — never copy/paste Pydantic models or prompt strings
- The system + user prompt in training data must be identical to production `classify_tables()`
- All scripts must work from the repo root: `python finetune/scripts/...`
- Use `uv` or the existing venv — do not install packages globally
- If a downloaded schema fails to load (bad SQL, unsupported syntax), skip it gracefully and log