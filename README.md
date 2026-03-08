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

## Quick Start

**1. Install prerequisites**
```bash
# Install Ollama (default provider)
curl -fsSL https://ollama.com/install.sh | sh
ollama pull gemma3-data

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
