# CLI Reference

## Top-level

```
schemalytics [OPTIONS] COMMAND [ARGS]
```

| Command | Description |
|---------|-------------|
| `generate` | Full pipeline — extract schema, AI planning, refinement loop, generate dbt project |
| `extract` | Schema extraction only — outputs JSON |

---

## `schemalytics generate`

Run the full pipeline: extract schema → 5-agent AI pipeline → refinement loop → generate dbt project.

```bash
schemalytics generate [OPTIONS]
```

### Options

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--connection` | `-c` | Yes | PostgreSQL connection string |
| `--output` | `-o` | Yes | Output directory for the dbt project |
| `--name` | `-n` | No | dbt project name (default: `my_dbt_project`) |

### Examples

```bash
# Minimal
schemalytics generate \
  -c postgresql://user:pass@localhost/mydb \
  -o ./dbt_project

# With project name
schemalytics generate \
  -c postgresql://user:pass@localhost/mydb \
  -o ./dbt_project \
  -n my_project_name

# Using Anthropic instead of local Ollama
SCHEMALYTICS_LLM_PROVIDER=anthropic \
ANTHROPIC_API_KEY=sk-ant-... \
schemalytics generate \
  -c postgresql://user:pass@localhost/mydb \
  -o ./dbt_project
```

---

## `schemalytics extract`

Extract the database schema to a JSON file without running the full pipeline. Useful for inspecting what Schemalytics sees before committing to generation.

```bash
schemalytics extract [OPTIONS]
```

### Options

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--connection` | `-c` | Yes | PostgreSQL connection string |
| `--output` | `-o` | Yes | Output file path for the JSON schema |

### Example

```bash
schemalytics extract \
  -c postgresql://user:pass@localhost/mydb \
  -o schema.json
```

### Output format

```json
{
  "tables": [
    {
      "name": "orders",
      "schema_name": "public",
      "columns": [
        {"name": "order_id", "data_type": "integer", "nullable": false},
        {"name": "customer_id", "data_type": "integer", "nullable": true},
        {"name": "order_date", "data_type": "date", "nullable": true}
      ],
      "primary_key": ["order_id"],
      "foreign_keys": [
        {
          "column": "customer_id",
          "references_table": "customers",
          "references_column": "customer_id"
        }
      ]
    }
  ]
}
```

---

## Connection String Format

Standard PostgreSQL connection string:

```
postgresql://[user]:[password]@[host]:[port]/[database]
```

Examples:
```bash
# Local default
postgresql://user:password@localhost:5432/mydb

# Remote with non-standard port
postgresql://admin:secret@db.example.com:5433/analytics

# With special characters in password (URL-encode them)
postgresql://user:p%40ssword@localhost/mydb
```

---

## LLM Provider Environment Variables

```bash
# Ollama (default) — requires Ollama running at localhost:11434
# Model: gemma3-data
SCHEMALYTICS_LLM_PROVIDER=ollama   # or omit

# Anthropic Claude — requires API key
# Model: claude-sonnet-4-20250514
SCHEMALYTICS_LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=sk-ant-...
```

---

## Public Python API

Schemalytics can also be used programmatically:

```python
from schemalytics import (
    Schema,
    ModelingPlan,
    PipelineContext,
    extract_schema,
    generate_dbt_project,
)
from schemalytics.planner import run_pipeline

# Extract schema
schema = extract_schema("postgresql://user:pass@localhost/mydb")

# Run full interactive pipeline
result = run_pipeline(schema)
if result is None:
    # User cancelled
    exit()

modeling_plan, pipeline_ctx = result

# Generate dbt project
generate_dbt_project(
    schema=schema,
    plan=modeling_plan,
    output_dir="./dbt_project",
    project_name="my_project",
    business_type=pipeline_ctx.business_type,
    context=pipeline_ctx,
)
```
