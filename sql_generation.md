# SQL Generation Updates for Naming Conventions

## Changes Made to planner.py

✅ **LLM prompts updated:**
- Bronze: `stg_<schema>_<table>` (e.g., `stg_public_customers`)
- Gold: `agg_<grain>_<metric>` (e.g., `agg_daily_revenue`)

✅ **Display function updated:**
- Shows correct model names in user-facing plan

## Additional Updates Needed in generators/dbt.py

You'll need to update the SQL generation code to match the new naming:

### 1. Bronze Models
```python
# OLD:
for table in plan.bronze:
    sql = f"""-- Bronze: Raw passthrough from source
{{{{ config(materialized='view') }}}}

select *
from {{{{ source('raw', '{table}') }}}}
"""
    (base / "models" / "bronze" / f"bronze_{table}.sql").write_text(sql)

# NEW:
bronze_schema = "public"  # Get from schema object or plan
for table in plan.bronze:
    sql = f"""-- Bronze: Raw passthrough from source
{{{{ config(materialized='view') }}}}

select *
from {{{{ source('raw', '{table}') }}}}
"""
    (base / "models" / "bronze" / f"stg_{bronze_schema}_{table}.sql").write_text(sql)
```

### 2. Gold Models
```python
# OLD:
for gold in plan.gold:
    sql = f"""-- Gold: {gold.name}
-- {gold.description}
{{{{ config(materialized='table') }}}}

select
    date_trunc('{grain_func}', {gold.date_column}) as {gold.grain}_date,
{chr(10).join(dims_sql)}
{(','+chr(10)).join(metrics_sql)}
from {{{{ ref('{gold.source_fact}') }}}}
group by 1{', ' + ', '.join(str(i+2) for i in range(len(gold.dimensions))) if gold.dimensions else ''}
"""
    (base / "models" / "gold" / f"{gold.name}.sql").write_text(sql)

# NEW (no change needed - gold.name already has "agg_" prefix from LLM)
# Just verify the model names in schema.yml match
```

### 3. schema.yml Files

Update references in schema.yml files:

```yaml
# OLD bronze schema.yml:
models:
  - name: bronze_customers
  
# NEW bronze schema.yml:
models:
  - name: stg_public_customers
```

```yaml
# OLD gold schema.yml:
models:
  - name: gold_daily_revenue
  
# NEW gold schema.yml:
models:
  - name: agg_daily_revenue
```

### 4. README.md Generation

Update README to reflect new naming:

```markdown
## Structure
- **bronze/**: Raw passthrough from source (14 models named stg_public_*)
- **silver/dimensions/**: Dimensional models (9 models named dim_*)
- **silver/facts/**: Fact tables (5 models named fct_*)
- **gold/**: Pre-aggregated metrics (8 models named agg_*)
```

## Testing Checklist

After updating dbt.py:
- [ ] Bronze models generated as `stg_schema_table.sql`
- [ ] Gold models generated as `agg_grain_metric.sql`
- [ ] schema.yml files use correct model names
- [ ] Refs in SQL match model names
- [ ] README reflects new naming
- [ ] Test with sample database

## Schema Name Source

To get the schema name for bronze models:
```python
# Option 1: From schema object
bronze_schema = schema.tables[0].schema_name if schema.tables else "public"

# Option 2: Add to plan_dict
plan_dict.get("bronze_schema", "public")

# Option 3: From context or config
context.source_schema or "public"
```

The LLM already includes `"bronze_schema": "public"` in the JSON output, so you can use:
```python
bronze_schema = plan_dict.get("bronze_schema", "public")
```