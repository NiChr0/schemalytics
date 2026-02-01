# Schemalytics

**Semantic Layer for Self-Service Analytics**

Schemalytics transforms your database into an LLM-ready semantic layer that enables self-service analytics. It analyzes your schema, generates dimensional models, and creates comprehensive metadata that LLMs can use to write accurate SQL queries—all running locally with complete privacy.

The tool generates a complete dbt project as the implementation layer, following dimensional modeling best practices with medallion architecture (Bronze → Silver → Gold).

**Key features:**
- **Semantic layer generation** - LLM-ready metadata with metrics, relationships, and query patterns
- **Self-service analytics** - Enable natural language queries against your data
- **Privacy-first** - Runs on local LLMs (Ollama), no data leaves your machine
- **Interactive refinement** - Perfect your data model through natural language feedback
- **Industry templates** - Pre-configured patterns for e-commerce, SaaS, fintech, and more

## Quick Start

**1. Install prerequisites**
```bash
# Install Ollama
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b

# Install Schemalytics  
pip install schemalytics
```

**2. Generate semantic layer + dbt project**
```bash
schemalytics generate \
  -c postgresql://localhost/mydb \
  -o ./dbt_project
```

**3. Interactive refinement**
- AI generates initial plan with concrete specifications
- You refine with natural language ("make revenue weekly", "add customer LTV")
- Approve when ready

## What You Get

- **Semantic layer** (`semantic_layer.yml`) - Complete metadata for LLM-powered analytics
- **Bronze models** - Raw data staging layer
- **Silver models** - Facts and dimensions (star schema)
- **Gold models** - Pre-aggregated metrics for performance
- **Documentation** - Auto-generated schema.yml files with tests

## License

Apache 2.0 • Built by [NiChr0](https://github.com/NiChr0)
