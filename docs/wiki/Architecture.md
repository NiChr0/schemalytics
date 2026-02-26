# Architecture

## Pipeline Overview

```
PostgreSQL DB
     │
     │  SQLAlchemy (extractors/postgres.py)
     ▼
Schema object (Pydantic)
     │
     │  Interactive prompts or context.yaml (planner.py)
     ▼
BusinessContext object (Pydantic)
     │
     │  FK graph heuristics (planner.py)
     ▼
TableClassifications[]
     │
     │  LLM via Ollama HTTP API (planner.py + llm.py)
     ▼
ModelingPlan object (Pydantic)  ←──── Interactive refinement loop
     │
     │  Jinja2 templates (generators/dbt.py + templates.py)
     ▼
dbt project on disk
```

---

## Module Map

| File | Responsibility |
|------|---------------|
| `cli.py` | Click CLI entry point — wires the pipeline together |
| `models.py` | All Pydantic data models |
| `llm.py` | Ollama HTTP client |
| `planner.py` | Context gathering, FK classification, LLM planning, refinement loop |
| `templates.py` | Jinja2 SQL templates for all dbt model types |
| `industry_taxonomy.py` | 14+ industry presets with entities, goals, metrics |
| `extractors/postgres.py` | SQLAlchemy schema extraction |
| `generators/dbt.py` | dbt project file generation |

---

## Data Models (models.py)

```
Schema
  └── tables: list[Table]
        ├── name: str
        ├── schema: str
        ├── columns: list[Column]
        │     ├── name: str
        │     ├── type: str
        │     └── nullable: bool
        ├── primary_keys: list[str]
        └── foreign_keys: list[ForeignKey]
              ├── column: str
              ├── references_table: str
              └── references_column: str

BusinessContext
  ├── industry: str
  ├── business_type: str
  ├── entities: list[str]
  ├── goals: list[str]
  ├── temporal: str          # "historical_tracking" | "current_only"
  └── grain: str             # "transaction_level" | "daily" | "weekly"

ModelingPlan
  ├── bronze: list[str]           # source table names
  ├── dimensions: list[DimensionPlan]
  │     ├── name: str             # "dim_customers"
  │     ├── source_table: str
  │     ├── scd_type: int         # 1 or 2
  │     ├── grain: str
  │     ├── primary_key: str
  │     └── columns: list[str]
  ├── facts: list[FactPlan]
  │     ├── name: str             # "fct_orders"
  │     ├── source_table: str
  │     ├── grain: str
  │     ├── date_column: str
  │     ├── foreign_keys: list[FKReference]
  │     └── measures: list[str]
  └── gold: list[GoldPlan]
        ├── name: str             # "agg_monthly_revenue"
        ├── source_fact: str
        ├── grain: str
        ├── date_column: str
        ├── metrics: list[MetricDefinition]
        │     ├── name: str
        │     ├── aggregation: str   # SUM, COUNT, AVG, MIN, MAX
        │     └── column: str
        └── description: str
```

---

## FK Graph Heuristics

Before the LLM generates a plan, Schemalytics classifies tables using FK graph analysis. This gives the LLM a reliable starting point.

**Rules:**

| Condition | Classification |
|-----------|----------------|
| 2+ outgoing FKs | `fact` (high confidence) |
| 2+ incoming FKs | `dimension` (high confidence) |
| 1 outgoing FK, 0 incoming | `dimension` (low confidence) |
| 0 outgoing, 1 incoming | `dimension` (medium confidence) |
| Bridge pattern (2 outgoing FKs to dimensions) | `bridge` |
| No FKs | `dimension` (standalone lookup) |

This is more reliable than name-based guessing ("orders_table" could be anything).

---

## LLM Integration

All LLM calls go through Ollama running on `localhost:11434`. No cloud APIs are used.

**Models:**
- `qwen-data:latest` — primary planning and classification model
- `qwen2.5-coder:7b` — fallback, also used for code-adjacent tasks

**Two LLM calls per run:**

1. **Generate** (`llm_generate_detailed_plan`) — initial plan from schema + context + heuristics
2. **Refine** (`llm_refine_plan`) — per-iteration plan amendment from user feedback

Each call receives the complete current state (stateless per call), which prevents context drift over multiple refinement rounds.

**JSON output handling:**

The LLM is prompted to return structured JSON. A regex fallback strips markdown code fences if the model wraps the JSON in them.

---

## SQL Generation

SQL is never generated directly by the LLM. All SQL comes from Jinja2 templates filled with data from the approved `ModelingPlan`.

**Templates:**

| Template | Output |
|----------|--------|
| `BRONZE_TEMPLATE` | `SELECT * FROM source(...)` view |
| `DIM_SCD1_TEMPLATE` | Dimension with simple overwrites |
| `DIM_SCD2_TEMPLATE` | Dimension with `valid_from`/`valid_to` history |
| `FACT_TEMPLATE` | Fact table with surrogate keys and measure columns |
| `GOLD_AGGREGATE_TEMPLATE` | Pre-aggregated metrics with `DATE_TRUNC` |

This ensures generated SQL is always syntactically valid and follows consistent patterns, regardless of LLM quality.

---

## Component Interaction

```
cli.py
  │
  ├── extract_schema()           extractors/postgres.py
  │
  ├── gather_context_interactively()   planner.py
  │     └── industry_taxonomy.py       (presets)
  │
  ├── classify_by_fk_graph()     planner.py
  │
  ├── interactive_refinement_loop()  planner.py
  │     ├── llm_generate_detailed_plan()  planner.py → llm.py → Ollama
  │     ├── display_concrete_plan()       planner.py
  │     ├── llm_refine_plan()             planner.py → llm.py → Ollama
  │     ├── show_diff()                   planner.py
  │     └── convert_plan_dict_to_modeling_plan()  planner.py → models.py
  │
  └── generate_dbt_project()     generators/dbt.py
        └── templates.py          (Jinja2 SQL)
```
