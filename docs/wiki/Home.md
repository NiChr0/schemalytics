# Schemalytics Wiki

**Schemalytics** transforms PostgreSQL databases into LLM-ready semantic layers for self-service analytics. It analyzes your schema through a 5-agent AI pipeline, generates a complete dimensional model through an interactive refinement loop, and outputs a production-ready dbt project — running locally by default with full privacy.

---

## What It Does

```
PostgreSQL DB  →  5-Agent AI Pipeline  →  dbt Project + Semantic Layer
```

1. Connects to your PostgreSQL database and extracts the full schema
2. Agent 1 infers your industry and business domain from schema metadata
3. Agent 2 suggests metrics, goals, and measurement grain
4. Agent 3 classifies tables as facts, dimensions, bridge, or reference using FK graph heuristics
5. You review a consolidated summary and correct anything wrong
6. Agent 4 generates a full Bronze/Silver/Gold modeling plan
7. You refine the plan with natural language feedback until approved
8. Outputs a complete dbt project with a semantic layer YAML

---

## Wiki Pages

| Page | Description |
|------|-------------|
| [Installation](Installation) | Prerequisites, install steps, verify setup |
| [Getting Started](Getting-Started) | Your first run from zero to dbt project |
| [CLI Reference](CLI-Reference) | All commands, flags, and options |
| [Architecture](Architecture) | Technical pipeline, data flow, component map |
| [Contributing](Contributing) | Development setup and contribution guide |
| [Troubleshooting](Troubleshooting) | Common issues and fixes |

---

## Quick Start

```bash
# 1. Install prerequisites
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen3-30b-data
ollama pull nichr0/schemalytics-classification-agent
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

- **Version:** 0.2.0
- **License:** Apache 2.0
- **Python:** 3.10+
- **LLM:** Local Ollama (default) or Anthropic Claude (via env var)
- **Classification Agent:** `schemalytics-classification-agent` (fine-tuned Qwen3.5-4B, 2.6 GB)
- **GitHub:** https://github.com/NiChr0/schemalytics
- **PyPI:** https://pypi.org/project/schemalytics/
