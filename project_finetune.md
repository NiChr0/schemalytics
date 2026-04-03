# Schemalytics — Fine-Tuned Models

Three Qwen3.5-4B models have been fine-tuned for the Schemalytics pipeline and published to Ollama Hub.
They are optional drop-in replacements for the default `qwen3-30b-data` model.

---

## Available Models

| Model | Ollama Hub | Agent | Task |
|-------|-----------|-------|------|
| Classification Agent | `nichr0/schemalytics-classification-agent` | Agent 3 | Classify tables as fact/dimension/bridge/reference |
| Silver Agent | `nichr0/schemalytics-silver-agent` | Agent 4a | Generate Silver layer plan (dim_*, fct_*) |
| Gold Agent | `nichr0/schemalytics-gold-agent` | Agent 4b | Generate Gold layer plan (agg_*) |

All three are **Qwen3.5-4B QLoRA** (r=8, α=16), trained via Unsloth on an RTX 3090.

---

## Usage

Pull the models once:

```bash
ollama pull nichr0/schemalytics-classification-agent
ollama pull nichr0/schemalytics-silver-agent
ollama pull nichr0/schemalytics-gold-agent
```

To use a fine-tuned model, set `SCHEMALYTICS_OLLAMA_MODEL` before running the pipeline.
Currently this replaces the default model for **all** agent calls. Per-agent model selection
is planned but not yet implemented.

```bash
# Example: use classification agent for a classification-heavy session
SCHEMALYTICS_OLLAMA_MODEL=nichr0/schemalytics-classification-agent \
schemalytics generate -c postgresql://...
```

---

## Training Details

### Classification Agent (`nichr0/schemalytics-classification-agent`)

- **Task:** Given a database schema + FK heuristics → output JSON with fact/dimension/bridge/reference role per table
- **Dataset:** Spider benchmark schemas + enterprise schemas (GLPI, Northwind, AdventureWorks, etc.) — gretelai excluded
- **Training examples:** 147 schemas labeled via Claude Haiku (Sonnet fallback for 33 failures)
- **Training loss:** 0.336 | **Eval loss:** 0.115
- **Context:** 12,288 tokens | **Max output:** 2,048 tokens
- **Adapters:** `finetune/cuda/adapters-qwen3.5-4b-v6/checkpoint-400`
- **Branch:** `retrain_agent_3`

### Silver Agent (`nichr0/schemalytics-silver-agent`)

- **Task:** Given schema + classified tables → output Silver modeling plan (dim_*/fct_* models with grain, measures, FK keys)
- **Dataset:** Same schema corpus as classification agent
- **Training loss:** ~0.06 range
- **Context:** 12,288 tokens | **Max output:** 4,096 tokens
- **Adapters:** `finetune/cuda/adapters-silver-v2/checkpoint-600`
- **Branch:** `finetune_vast_ai`

### Gold Agent (`nichr0/schemalytics-gold-agent`)

- **Task:** Given Silver plan → output Gold aggregation plan (agg_* models with grain and metrics)
- **Dataset:** Same schema corpus as silver
- **Training loss:** ~0.06 range
- **Context:** 8,192 tokens | **Max output:** 2,048 tokens
- **Adapters:** `finetune/cuda/adapters-gold-v2/checkpoint-600`
- **Branch:** `finetune_vast_ai`

---

## Fine-Tune Pipeline

All training ran on an RTX 3090 (24 GB VRAM) via vast.ai / RunPod.

```
1. Extract schemas          finetune/scripts/download_and_extract_complex.py
                            finetune/scripts/extract_spider.py
                            → finetune/extracted_complex/
                            → finetune/extracted_spider/
                            → finetune/extracted/
                            → finetune/extracted_new/

2. Label classification     finetune/scripts/label_silver_classification.py
   (Agent 3 training data)  → finetune/labeled_silver_class/

3. Label silver/gold        finetune/scripts/label_complex.py
   (Agents 4a/4b data)      finetune/scripts/label_silver.py
                            finetune/scripts/label_gold.py
                            → finetune/labeled_complex/
                            → finetune/labeled/

4. Build dataset            finetune/scripts/05_build_dataset.py
                            → finetune/dataset/train.jsonl
                            → finetune/dataset/eval.jsonl

5. Train on GPU             finetune/cuda/finetune_silver.py
                            finetune/cuda/finetune_gold.py
                            bash finetune/cuda/setup_vastai.sh both

6. Export + push            bash finetune/cuda/setup_vastai.sh export
   (GGUF Q4_K_M)            → nichr0/schemalytics-silver-agent
                            → nichr0/schemalytics-gold-agent
```

---

## Roadmap

- [ ] Per-agent model env vars (`SCHEMALYTICS_AGENT3_MODEL`, `SCHEMALYTICS_SILVER_MODEL`, `SCHEMALYTICS_GOLD_MODEL`)
- [x] Retrain classification agent on expanded dataset (147 schemas, gretelai excluded)
- [x] Publish updated classification agent to Ollama Hub
