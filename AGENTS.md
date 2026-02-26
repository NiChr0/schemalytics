# Schemalytics — Agent Context

> Load this file first for any task on this repo.
> For task-specific workflows, also load: `dev.md`, `testing.md`, or `release.md`.

---

## Project Overview

**Schemalytics** is an open-source CLI tool that automates dbt project generation from PostgreSQL databases using local LLMs (Ollama). It produces a complete medallion architecture dbt project (Bronze → Silver → Gold) with a semantic layer for LLM-powered self-service analytics.

- **PyPI:** `pip install schemalytics`
- **GitHub:** `https://github.com/NiChr0/schemalytics`
- **License:** Apache 2.0
- **Python:** 3.10+

---

## Repo Structure

```
schemalytics/
├── schemalytics/
│   ├── cli.py                  # Click CLI — entry point (generate, extract commands)
│   ├── models.py               # Pydantic models (Schema, BusinessContext, ModelingPlan, etc.)
│   ├── planner.py              # Core logic: FK graph classification, LLM planning, refinement loop
│   ├── llm.py                  # Ollama HTTP client
│   ├── templates.py            # Jinja2 dbt SQL templates
│   ├── industry_taxonomy.py    # 14+ industry presets with entities/goals/metrics
│   ├── extractors/
│   │   └── postgres.py         # SQLAlchemy schema extraction
│   └── generators/
│       └── dbt.py              # dbt project file generation
├── pyproject.toml              # Build config, dependencies, entry points
├── README.md
├── AGENTS.md                   # ← you are here (load this first)
├── dev.md                      # Agent: feature development workflow
├── testing.md                  # Agent: testing & validation workflow
└── release.md                  # Agent: PyPI release workflow
```

---

## Tech Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| CLI | `click` | Command routing |
| Schema extraction | `sqlalchemy`, `psycopg2-binary` | PostgreSQL introspection |
| LLM integration | `httpx` → Ollama HTTP API | Local LLM calls |
| Data validation | `pydantic` v2 | All internal models |
| SQL generation | `jinja2` | Template-based, not pure LLM output |
| Config files | `pyyaml` | `context.yaml` input |

**LLM models used (local Ollama only):**
- `qwen-data:latest` — planning and classification
- `qwen2.5-coder:7b` — code-adjacent generation

---

## Core Workflow

```
PostgreSQL DB
    ↓ extract_schema() [extractors/postgres.py]
Schema (Pydantic)
    ↓ gather_context_interactively() [planner.py]
BusinessContext (Pydantic)
    ↓ classify_by_fk_graph() [planner.py]
TableClassifications[]
    ↓ interactive_refinement_loop() [planner.py] ← LLM + user loop
ModelingPlan (Pydantic)
    ↓ generate_dbt_project() [generators/dbt.py]
dbt project on disk
```

---

## Key Design Decisions

- **Template-based SQL generation** — Jinja2 fills templates; LLM never writes raw SQL directly. Do not change this.
- **FK graph heuristics** — Tables with many outgoing FKs = facts; many incoming FKs = dimensions. More reliable than name-based guessing.
- **Local LLM only** — No cloud API calls. Ollama must be running locally. Never add cloud API dependencies.
- **No dbt execution** — Schemalytics generates code files only. Users run `dbt run` themselves. Do not add dbt execution logic.
- **Privacy-first** — No telemetry, no external calls except Ollama on localhost.

---

## Development Environment Setup

```bash
# Clone and install in editable mode
git clone https://github.com/NiChr0/schemalytics.git
cd schemalytics
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Prerequisites
curl -fsSL https://ollama.com/install.sh | sh
ollama pull qwen2.5-coder:7b

# Test database (Northwind via Docker)
docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres ghcr.io/nichr0/northwind-postgres:latest
```

---

## CLI Commands

```bash
# Full pipeline
schemalytics generate -c postgresql://user:pass@localhost/db -o ./dbt_project

# Schema extraction only
schemalytics extract -c postgresql://user:pass@localhost/db -o schema.json
```

---

## Agent Workflows

For agentic tasks, load the relevant agent doc before starting:

| Task | Agent doc |
|------|-----------|
| Add a feature or fix a bug | `dev.md` |
| Run tests or validate output | `testing.md` |
| Publish a new version to PyPI | `release.md` |
