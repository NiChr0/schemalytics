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
| `--name` | `-n` | No | dbt project name (default: `schemalytics_project`) |

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

## Environment Variables

```bash
# LLM provider (default: ollama)
SCHEMALYTICS_LLM_PROVIDER=ollama      # or omit — uses Ollama at localhost:11434
SCHEMALYTICS_LLM_PROVIDER=anthropic   # use Anthropic Claude instead

# Anthropic API key (required when provider=anthropic)
# Model: claude-sonnet-4-20250514
ANTHROPIC_API_KEY=sk-ant-...

# Ollama general model — used by Agents 1, 2, 5 (default: gemma3:4b)
SCHEMALYTICS_OLLAMA_MODEL=gemma3:4b

# Per-agent model overrides — Agents 3, 4a, 4b use fine-tuned models by default
SCHEMALYTICS_AGENT3_MODEL=nichr0/schemalytics-classification-agent
SCHEMALYTICS_AGENT4A_MODEL=nichr0/schemalytics-silver-agent
SCHEMALYTICS_AGENT4B_MODEL=nichr0/schemalytics-gold-agent
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
