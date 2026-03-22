# Schemalytics

**Semantic Layer for Self-Service Analytics**

Schemalytics transforms your database into an LLM-ready semantic layer that enables self-service analytics. It analyzes your schema, generates dimensional models, and creates comprehensive metadata that LLMs can use to write accurate SQL queries—all running locally with complete privacy.

The tool generates a complete dbt project as the implementation layer, following dimensional modeling best practices with medallion architecture (Bronze → Silver → Gold).

**Key features:**
- **Semantic layer generation** - LLM-ready metadata with metrics, relationships, and query patterns
- **Self-service analytics** - Enable natural language queries against your data
- **Privacy-first** - Runs on local LLMs (Ollama) by default; Anthropic supported via env var
- **Agentic pipeline** - Five focused AI agents infer industry, metrics, and table roles from schema metadata alone
- **Interactive refinement** - Review and refine the generated data model through natural language feedback
- **Fine-tuned classification** - Agent 3 uses `schemalytics-classification-agent`, a QLoRA fine-tuned Qwen3.5-4B model trained on real production schemas

## Quick Start

**1. Install prerequisites**
```bash
# Install Ollama (default provider)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-30b-data          # main pipeline model (Agents 1, 2, 4, 5)
ollama pull schemalytics-classification-agent  # Agent 3 fine-tuned classifier (see below)

# Install Schemalytics
pip install schemalytics
```

**2. Generate semantic layer + dbt project**
```bash
schemalytics generate \
  -c postgresql://localhost/mydb \
  -o ./dbt_project
```

**3. Agentic pipeline + interactive refinement**
- Agent 1 infers your industry and domain from schema metadata
- Agent 2 suggests metrics, goals, and reporting grain
- Agent 3 classifies each table as fact, dimension, bridge, or reference
- You review a consolidated summary and correct anything wrong
- Agent 4 generates a full modeling plan; you refine it with natural language ("make revenue weekly", "add customer LTV")
- Press Enter to approve and generate the dbt project

**Optional: use Anthropic instead of Ollama**
```bash
SCHEMALYTICS_LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-... \
schemalytics generate -c postgresql://localhost/mydb -o ./dbt_project
```

## Classification Agent (Agent 3)

Agent 3 uses a dedicated fine-tuned model — `schemalytics-classification-agent` — specialized for table classification across production databases.

**Model details:**
- Base: `unsloth/Qwen3.5-4B` (QLoRA, Q4\_K\_M quantized, 2.6 GB)
- Trained on 327 real-world schemas including GLPI (441 tables), OpenEMR (282), PrestaShop (242), OpenCart (136), Icinga (66), and others
- Train loss: 0.055 · Eval loss: 0.058 (no overfitting)

**Download and use:**
```bash
# Pull the model from Ollama Hub
ollama pull nichr0/schemalytics-classification-agent

# Use it for Agent 3 classification
SCHEMALYTICS_OLLAMA_MODEL=schemalytics-classification-agent \
schemalytics generate -c postgresql://... -o ./dbt_project
```

> **Note:** Attribution — `schemalytics-classification-agent` is built on Qwen3.5 by Alibaba Cloud (Qwen License).

## What You Get

- **Semantic layer** (`semantic_layer.yml`) - Complete metadata for LLM-powered analytics
- **Bronze models** - Raw data staging layer (`stg_<schema>_<table>`)
- **Silver models** - Facts (`fct_*`) and dimensions (`dim_*`) in star schema
- **Gold models** - Pre-aggregated metrics (`agg_<grain>_<metric>`)
- **Documentation** - Auto-generated schema.yml files

## CLI

```bash
# Full agentic pipeline
schemalytics generate -c postgresql://user:pass@localhost/db -o ./dbt_project

# Schema extraction only
schemalytics extract -c postgresql://user:pass@localhost/db -o schema.json
```

## License

Apache 2.0 • Built by [NiChr0](https://github.com/NiChr0)

> `schemalytics-classification-agent` is based on Qwen3.5 (Qwen License) by Alibaba Cloud.
