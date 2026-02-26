# Schemalytics Wiki

**Schemalytics** transforms PostgreSQL databases into LLM-ready semantic layers for self-service analytics. It analyzes your schema, generates a complete dimensional model through an interactive AI-powered refinement loop, and outputs a production-ready dbt project — all running locally with full privacy.

---

## What It Does

```
PostgreSQL DB  →  Interactive AI Refinement  →  dbt Project + Semantic Layer
```

1. Connects to your PostgreSQL database and extracts the full schema
2. Asks for your industry and analytical goals
3. Classifies tables as facts and dimensions using FK graph heuristics
4. Generates a detailed modeling plan and lets you refine it with natural language
5. Outputs a complete dbt project (Bronze → Silver → Gold) with a semantic layer YAML

---

## Wiki Pages

| Page | Description |
|------|-------------|
| [Installation](Installation) | Prerequisites, install steps, verify setup |
| [Getting Started](Getting-Started) | Your first run from zero to dbt project |
| [CLI Reference](CLI-Reference) | All commands, flags, and options |
| [Interactive Refinement](Interactive-Refinement) | How to use the AI refinement loop |
| [Architecture](Architecture) | Technical pipeline, data flow, component map |
| [Output Structure](Output-Structure) | What gets generated and how to use it |
| [Industry Templates](Industry-Templates) | 14+ pre-configured industry presets |
| [Semantic Layer](Semantic-Layer) | What semantic_layer.yml contains and how to use it |
| [Configuration](Configuration) | context.yaml format and options |
| [Troubleshooting](Troubleshooting) | Common issues and fixes |
| [Contributing](Contributing) | Development setup and contribution guide |

---

## Quick Start

```bash
# 1. Install prerequisites
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b
pip install schemalytics

# 2. Run
schemalytics generate \
  -c postgresql://localhost/mydb \
  -o ./dbt_project

# 3. After approval, run your dbt project
cd dbt_project
dbt run
```

---

## Key Facts

- **Version:** 0.1.3
- **License:** Apache 2.0
- **Python:** 3.10+
- **LLM:** Local Ollama only (no cloud API calls)
- **GitHub:** https://github.com/NiChr0/schemalytics
- **PyPI:** https://pypi.org/project/schemalytics/
