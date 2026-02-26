# CLI Reference

## Top-level

```
schemalytics [OPTIONS] COMMAND [ARGS]
```

| Command | Description |
|---------|-------------|
| `generate` | Full pipeline — extract schema, refine plan, generate dbt project |
| `extract` | Schema extraction only — outputs JSON |

---

## `schemalytics generate`

Run the full pipeline: extract schema → interactive context → AI planning → refinement loop → generate dbt project.

```bash
schemalytics generate [OPTIONS]
```

### Options

| Flag | Short | Required | Description |
|------|-------|----------|-------------|
| `--connection` | `-c` | Yes | PostgreSQL connection string |
| `--output` | `-o` | Yes | Output directory for the dbt project |
| `--name` | `-n` | No | dbt project name (default: `my_dbt_project`) |
| `--context-file` | `-x` | No | Path to a `context.yaml` file (skips interactive prompts) |

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

# Non-interactive using context file
schemalytics generate \
  -c postgresql://user:pass@localhost/mydb \
  -o ./dbt_project \
  -x context.yaml

# Full example
schemalytics generate \
  -c postgresql://postgres:postgres@localhost:5432/northwind \
  -o ./northwind_dbt \
  -n northwind \
  -x context.yaml
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
      "schema": "public",
      "columns": [
        {"name": "order_id", "type": "integer", "nullable": false},
        {"name": "customer_id", "type": "integer", "nullable": true},
        {"name": "order_date", "type": "date", "nullable": true}
      ],
      "primary_keys": ["order_id"],
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
postgresql://postgres:postgres@localhost:5432/mydb

# Remote with non-standard port
postgresql://admin:secret@db.example.com:5433/analytics

# With special characters in password (URL-encode them)
postgresql://user:p%40ssword@localhost/mydb
```

---

## Environment Variables

You can set the connection string as an environment variable to avoid passing it on the command line:

```bash
export SCHEMALYTICS_CONNECTION="postgresql://user:pass@localhost/mydb"
```

> Note: Environment variable support depends on your shell configuration. The `-c` flag always takes precedence.

---

## Public Python API

Schemalytics can also be used programmatically:

```python
from schemalytics import (
    Schema,
    BusinessContext,
    ModelingPlan,
    extract_schema,
    generate_dbt_project,
)

# Extract schema
schema = extract_schema("postgresql://user:pass@localhost/mydb")

# Generate dbt project from an approved ModelingPlan
generate_dbt_project(plan, output_path="./dbt_project", project_name="my_project")
```
