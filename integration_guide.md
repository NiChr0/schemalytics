# Integration Guide

> Technical reference for the Schemalytics pipeline. For architecture context see `docs/wiki/Architecture.md`. For contributing guidelines see `docs/wiki/Contributing.md`.

---

## Pipeline Entry Point

`run_pipeline(schema)` in `schemalytics/planner.py` is the single function that drives the full interactive pipeline.

```python
from schemalytics.extractors.postgres import extract_schema
from schemalytics.planner import run_pipeline
from schemalytics.generators.dbt import generate_dbt_project

schema = extract_schema("postgresql://user:pass@host/dbname")

result = run_pipeline(schema)
if result is None:
    # User cancelled
    return

modeling_plan, pipeline_ctx = result

generate_dbt_project(
    schema,
    modeling_plan,
    output_dir="./dbt_project",
    project_name="my_project",
    business_type=pipeline_ctx.business_type,
    context=pipeline_ctx,
)
```

---

## Agent Functions

All agent functions live in `schemalytics/planner.py`. All LLM calls go through `schemalytics.llm.query_structured()`.

### `infer_industry(schema, user_feedback=None) -> IndustryInference`

Reads table names, column names, and FK relationships to determine industry and business type.

```python
from schemalytics.planner import infer_industry

result = infer_industry(schema)
print(result.industry)        # e.g. "retail"
print(result.business_type)   # e.g. "wholesale_distribution"
print(result.confidence)      # 1, 2, or 3
print(result.reasoning)
```

### `suggest_metrics(schema, industry, user_feedback=None) -> MetricsSuggestion`

Suggests key metrics, analytical goals, and measurement grain based on schema and industry.

```python
from schemalytics.planner import suggest_metrics

result = suggest_metrics(schema, industry_inference)
print(result.metrics)          # e.g. ["total_revenue", "order_count"]
print(result.goals)            # e.g. ["revenue_reporting", "supplier_performance"]
print(result.suggested_grain)  # e.g. "order_line"
print(result.confidence)
```

### `classify_tables(schema, context, user_feedback=None) -> list[TableClassificationResult]`

Classifies each table as `fact`, `dimension`, `bridge`, or `reference`. Uses FK graph heuristics as a prior.

```python
from schemalytics.planner import classify_tables

results = classify_tables(schema, partial_context)
for r in results:
    print(r.table_name, r.role, r.confidence)
```

### `generate_modeling_plan(schema, context) -> ModelingPlan`

Produces the full Bronze/Silver/Gold modeling plan from the finalized pipeline context.

```python
from schemalytics.planner import generate_modeling_plan

plan = generate_modeling_plan(schema, pipeline_ctx)
print(plan.bronze)      # list of bronze model names
print(plan.dimensions)  # list of DimensionPlan
print(plan.facts)       # list of FactPlan
print(plan.gold)        # list of GoldPlan
```

### `refine_modeling_plan(plan, feedback, schema, context) -> ModelingPlan`

Applies natural language feedback to produce a revised plan. Stateless: each call receives the full current plan.

```python
from schemalytics.planner import refine_modeling_plan

new_plan = refine_modeling_plan(
    plan=current_plan,
    feedback="add a daily freight aggregate by shipper",
    schema=schema,
    context=pipeline_ctx,
)
```

---

## FK Graph Heuristics

`classify_by_fk_graph(schema)` runs before Agent 3 and returns preliminary classifications. These are passed to Agent 3 as a starting prior, not ground truth.

```python
from schemalytics.planner import classify_by_fk_graph

heuristics = classify_by_fk_graph(schema)
for h in heuristics:
    print(h.table.name, h.role)  # role: "fact" | "dimension" | "unknown"
```

Rules:
- 2+ outgoing FKs, 0 incoming → likely fact
- 2+ incoming FKs, 0 outgoing → likely dimension

---

## Pydantic Models

All pipeline data structures are defined in `schemalytics/models.py`.

| Model | Description |
|-------|-------------|
| `Schema` | Extracted database schema (tables, columns, PKs, FKs) |
| `IndustryInference` | Agent 1 output: industry, business_type, confidence |
| `MetricsSuggestion` | Agent 2 output: metrics, goals, grain, confidence |
| `TableClassificationResult` | Agent 3 output per table: role, confidence |
| `PipelineContext` | Consolidated context passed to Agents 4 and 5 |
| `ModelingPlan` | Full Bronze/Silver/Gold plan |
| `DimensionPlan` | Spec for a single dimension table |
| `FactPlan` | Spec for a single fact table — includes `measures` (bare numeric columns), `derived_measures` (computed `expression AS name`), and `factless` flag |
| `DerivedMeasure` | A computed column: `name` (SQL alias) + `expression` (SQL expression). Rendered in Silver as `expression AS name`; referenced by alias in Gold. |
| `MetricDefinition` | A Gold metric: `name`, `aggregation` (SUM/COUNT/COUNT_DISTINCT/AVG/MIN/MAX), `column` (bare column name or `*`) |
| `GoldPlan` | Spec for a single gold aggregate |

---

## LLM Abstraction

All agent calls go through one function:

```python
from schemalytics import llm
from schemalytics.models import MyOutputModel

result = llm.query_structured(
    system="You are a data engineer...",
    user=f"Schema:\n{schema_summary}",
    response_model=MyOutputModel,
)
# result is a validated MyOutputModel — no JSON parsing needed
```

`instructor` enforces the Pydantic schema and retries up to 3 times.

### Returning a list (instructor limitation)

`instructor` cannot return `list[T]` directly. Wrap in a container model:

```python
from pydantic import BaseModel

class _ResultList(BaseModel):
    items: list[MyItemModel]

result = llm.query_structured(system=..., user=..., response_model=_ResultList)
return result.items
```

---

## LLM Provider Configuration

```bash
# Ollama (default) — model: gemma3:4b for Agents 1, 2, 5
# Uses Ollama's OpenAI-compatible endpoint at localhost:11434/v1
SCHEMALYTICS_LLM_PROVIDER=ollama   # or omit (default)
SCHEMALYTICS_OLLAMA_MODEL=gemma3:4b  # override general model

# Per-agent fine-tuned model overrides (these are the defaults)
SCHEMALYTICS_AGENT3_MODEL=nichr0/schemalytics-classification-agent
SCHEMALYTICS_AGENT4A_MODEL=nichr0/schemalytics-silver-agent
SCHEMALYTICS_AGENT4B_MODEL=nichr0/schemalytics-gold-agent

# Anthropic Claude — model: claude-sonnet-4-20250514
SCHEMALYTICS_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

Only `llm.py` contains provider-specific logic. The rest of the pipeline is provider-agnostic.

---

## Generator

`generate_dbt_project()` in `schemalytics/generators/dbt.py` accepts either a `BusinessContext` or `PipelineContext` as the `context` parameter — both expose `.goals: list[str]`.

```python
from schemalytics.generators.dbt import generate_dbt_project

project_path = generate_dbt_project(
    schema=schema,
    plan=modeling_plan,
    output_dir="./dbt_project",
    project_name="northwind",
    business_type="wholesale_distribution",
    context=pipeline_ctx,          # PipelineContext or BusinessContext
)
```

SQL is generated from Jinja2 templates. The LLM never writes raw SQL.

**Derived measures** in `FactPlan.derived_measures` are rendered as `expression AS name` in the Silver fact SELECT. Gold models reference derived measures by their alias name — SQL expressions in Gold `column` fields are rejected by the sanitizer.

**Factless facts** (`FactPlan.factless = True`) are facts with no numeric measures — the fact table records the occurrence of an event. Gold models over factless facts use `COUNT(*)` with column `"*"` in `MetricDefinition`.

---

## Output Structure

```
./dbt_project/
  dbt_project.yml
  sources.yml
  models/
    bronze/            stg_<schema>_<table>.sql    (materialized view)
    silver/
      dimensions/      dim_*.sql                   (SCD1 or SCD2 table)
      facts/           fct_*.sql                   (table)
    gold/              agg_<grain>_<name>.sql       (table)
  semantic_layer.yml
  README.md
```

---

## Testing

Quick test reference:

```bash
# Unit tests (no LLM or DB needed)
pytest tests/test_agents.py -v

# Integration tests (requires Ollama + Northwind)
SCHEMALYTICS_INTEGRATION=1 pytest tests/test_integration.py -v
```
