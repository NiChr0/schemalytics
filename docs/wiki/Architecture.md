# Architecture

## Pipeline Overview

```
PostgreSQL DB
     │
     │  SQLAlchemy (extractors/postgres.py)
     ▼
Schema object (Pydantic)
     │
     │  run_pipeline() — 5-agent interactive pipeline (planner.py)
     ▼
PipelineContext object (Pydantic)   ←── Agents 1-3 + Summary Gate
     │
     │  generate_modeling_plan() — Agent 4 (Silver + Gold)
     ▼
ModelingPlan object (Pydantic)  ←──── Refinement loop — Agent 5
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
| `llm.py` | LLM provider abstraction (Ollama or Anthropic via instructor) |
| `planner.py` | 5-agent pipeline, FK classification, sanitization, refinement loop |
| `templates.py` | Jinja2 SQL templates for all dbt model types |
| `extractors/postgres.py` | SQLAlchemy schema extraction |
| `generators/dbt.py` | dbt project file generation |

---

## Data Models (models.py)

```
Schema
  └── tables: list[Table]
        ├── name: str
        ├── schema_name: str
        ├── columns: list[Column]
        │     ├── name: str
        │     ├── data_type: str
        │     └── nullable: bool
        ├── primary_key: list[str]
        └── foreign_keys: list[ForeignKey]
              ├── column: str
              ├── references_table: str
              └── references_column: str

ModelingPlan
  ├── bronze: list[str]           # source table names
  ├── dimensions: list[DimensionPlan]
  │     ├── name: str             # "dim_customers"
  │     ├── source_table: str
  │     ├── scd_type: int         # 1 or 2
  │     ├── grain: str
  │     └── columns: list[str]    # auto-filled from schema by sanitizer
  ├── facts: list[FactPlan]
  │     ├── name: str             # "fct_orders"
  │     ├── source_table: str
  │     ├── grain: str
  │     ├── date_column: str
  │     ├── dimension_keys: list[str]
  │     ├── measures: list[str]           # bare numeric column names only
  │     ├── derived_measures: list[DerivedMeasure]
  │     │     ├── name: str              # SQL alias, e.g. "line_total"
  │     │     └── expression: str        # SQL expression, e.g. "qty * price"
  │     └── factless: bool               # True when no numeric measures exist
  └── gold: list[GoldPlan]
        ├── name: str             # "agg_monthly_revenue"
        ├── source_fact: str
        ├── grain: str            # "daily" | "monthly" | "yearly"
        ├── date_column: str
        ├── dimensions: list[str] # FK column names to group by
        ├── metrics: list[MetricDefinition]
        │     ├── name: str
        │     ├── aggregation: str   # SUM, COUNT, COUNT_DISTINCT, AVG, MIN, MAX
        │     └── column: str        # bare column name or "*" for COUNT(*)
        └── description: str

PipelineContext
  ├── industry: str
  ├── business_type: str
  ├── metrics: list[str]
  ├── goals: list[str]
  ├── grain: str
  └── table_classifications: list[TableClassificationResult]
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

Results feed Agent 3 as a prior — the agent validates and adjusts them.

---

## LLM Integration

All agent calls go through `llm.query_structured()` in `llm.py`. Two providers supported:

| Provider | Model | How to activate |
|----------|-------|----------------|
| Ollama (default) | `gemma3-data` | Default — Ollama at `localhost:11434` |
| Anthropic | `claude-sonnet-4-20250514` | `SCHEMALYTICS_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY` |

`instructor` wraps the client and enforces every response matches the target Pydantic model. Max retries: 3. No JSON parsing anywhere in the pipeline.

**LLM calls per run:** 5 agents × 1 call each, plus Agent 4 makes 2 calls (Silver + Gold separately) and Agent 5 makes 1 call per refinement iteration.

**Token budget management:** Ollama uses `num_ctx=12288` (fixed across all calls — changing it triggers a model reload). Each agent uses a dynamic `max_tokens` sized to its expected output, keeping `prompt_tokens + max_tokens` within the context window.

---

## Pipeline Contract (Silver → Gold)

Agent 4 runs as two sequential LLM calls with a sanitization step between them:

1. **Agent 4a** — generates Silver (bronze names, dimensions, facts)
2. **`_sanitize_plan()`** — validates all column names against the real schema, enforces that `measures` contains only numeric columns, validates derived measure expression references
3. **Agent 4b** — generates Gold, but only sees the **sanitized** Silver facts as context

This ensures Gold can only reference columns and derived measure aliases that actually exist and have been type-validated. Gold expressions (e.g. `qty * price`) are rejected — computed values must be declared as `DerivedMeasure` objects in Silver so Gold can reference them by alias.

---

## SQL Generation

SQL is never generated by the LLM. All SQL comes from Jinja2 templates filled with data from the approved `ModelingPlan`.

**Templates:**

| Template | Output |
|----------|--------|
| `BRONZE_TEMPLATE` | `SELECT * FROM source(...)` view |
| `DIM_SCD1_TEMPLATE` | Dimension with simple overwrites |
| `DIM_SCD2_TEMPLATE` | Dimension with `valid_from`/`valid_to` history |
| `FACT_TEMPLATE` | Fact table with surrogate keys, measures, and derived measures |
| `GOLD_AGGREGATE_TEMPLATE` | Pre-aggregated metrics with `DATE_TRUNC` |

Derived measures render as `expression AS name` in the Silver fact SELECT, making them available as named columns to Gold.

---

## Component Interaction

```
cli.py
  │
  ├── extract_schema()              extractors/postgres.py
  │
  └── run_pipeline(schema)          planner.py
        ├── infer_industry()          Agent 1 → llm.query_structured()
        ├── suggest_metrics()         Agent 2 → llm.query_structured()
        ├── classify_by_fk_graph()    FK heuristics (no LLM)
        ├── classify_tables()         Agent 3 → llm.query_structured() (batched)
        ├── [Summary Gate]            user review/correction
        ├── generate_modeling_plan()  Agent 4a (Silver) + sanitize + Agent 4b (Gold)
        └── refine_modeling_plan()    Agent 5 loop → llm.query_structured()

  └── generate_dbt_project()       generators/dbt.py
        └── templates.py             (Jinja2 SQL)
```
