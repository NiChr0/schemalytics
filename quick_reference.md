# Quick Reference: Schemalytics Generate

## Command

```bash
schemalytics generate -c postgresql://user:pass@host/dbname -o ./dbt_project
```

Optional flags: `-n <project_name>`

---

## Pipeline Overview

```
1. Schema extraction      — reads tables, columns, PKs, FKs
2. Agent 1                — infers industry and business type
3. Agent 2                — suggests metrics, goals, grain
4. Agent 3                — classifies tables (fact/dimension/bridge/reference)
5. Summary gate           — always runs; review and correct context
6. Agent 4                — generates Bronze/Silver/Gold modeling plan
7. Agent 5 (loop)         — refine plan with natural language feedback
8. dbt project generation — writes SQL files, schema.yml, README
```

---

## Confidence Rule (Agents 1-3)

| Confidence | Behavior |
|-----------|----------|
| 3 | Auto-proceeds, prints notification |
| 2 | Asks for confirmation or correction |
| 1 | Asks and explains why it's uncertain |

---

## Summary Gate

Always shown after Agent 3. Displays:

```
Industry / business type
Key metrics and goals
Grain
Table roles (facts, dimensions, bridge, reference)
```

Press **Enter** to accept. Type corrections in plain English to re-run Agents 1-3 with your input.

---

## Refinement Loop (Agent 5)

After Agent 4 shows the modeling plan, you can refine it with natural language:

### Change grain
```
"aggregate orders monthly, not daily"
"weekly is better for our reporting cadence"
```

### Add tables / metrics
```
"add customer lifetime value as a gold aggregate"
"we need a fact table for order returns"
"add units_returned as a measure to fct_order_lines"
```

### Remove tables
```
"drop the agg_supplier_sales table, we don't need it"
"remove us_states from bronze — it's not used"
```

### Reclassify
```
"employee_territories should be a bridge table, not dimension"
"region is a dimension, not reference"
```

### Add derived measures (computed columns)
```
"add line_total = quantity * unit_price as a derived measure on fct_order_details"
"add discount_amount = unit_price * discount on fct_orders"
```

Derived measures are rendered as `expression AS name` in Silver facts and can be referenced by alias in Gold aggregates.

### Complex changes
```
"split dim_customers into US and international based on country"
"change fct_orders to SCD2"
"move freight from fct_orders to fct_order_lines"
```

---

## Refinement Controls

| Input | Action |
|-------|--------|
| Natural language | Refine the plan (Agent 5 applies changes, shows diff) |
| Enter (blank) | Approve plan — proceed to generation |
| `cancel` | Abort — no project is generated |

---

## After Each Refinement

Schemalytics prints a diff:

```
Changes:
  + Added agg_daily_freight_by_shipper
  - Removed agg_supplier_sales
  ~ Modified fct_orders (updated measures)
```

---

## LLM Providers

```bash
# Default: local Ollama (no key needed)
schemalytics generate -c postgresql://...

# Anthropic Claude
SCHEMALYTICS_LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-... \
schemalytics generate -c postgresql://...
```

---

## Fine-Tuned Models

Three Qwen3.5-4B models are available on Ollama Hub as drop-in replacements for the default model:

| Model | Agent | Purpose |
|-------|-------|---------|
| `nichr0/schemalytics-classification-agent` | Agent 3 | Table classification (fact/dim/bridge/ref) |
| `nichr0/schemalytics-silver-agent` | Agent 4a | Silver layer plan (dim_*, fct_*) |
| `nichr0/schemalytics-gold-agent` | Agent 4b | Gold layer plan (agg_*) |

```bash
# Pull (one-time — required, these are the defaults for Agents 3, 4a, 4b)
ollama pull nichr0/schemalytics-classification-agent
ollama pull nichr0/schemalytics-silver-agent
ollama pull nichr0/schemalytics-gold-agent

# Per-agent override env vars
SCHEMALYTICS_AGENT3_MODEL=nichr0/schemalytics-classification-agent \
SCHEMALYTICS_AGENT4A_MODEL=nichr0/schemalytics-silver-agent \
SCHEMALYTICS_AGENT4B_MODEL=nichr0/schemalytics-gold-agent \
schemalytics generate -c postgresql://...

# Override general model (Agents 1, 2, 5) — default: gemma3:4b
SCHEMALYTICS_OLLAMA_MODEL=gemma3:4b schemalytics generate -c postgresql://...
```

---

## Output Structure

```
./dbt_project/
  dbt_project.yml
  sources.yml
  models/
    bronze/          stg_<schema>_<table>.sql  (views)
    silver/
      dimensions/    dim_*.sql                 (SCD1 or SCD2)
      facts/         fct_*.sql
    gold/            agg_*.sql
  semantic_layer.yml
  README.md
```

---

## Full Walkthrough

See `example_session.md` for a complete run against the Northwind database.
