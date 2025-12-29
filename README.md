# Schemalytics

Automated dbt project generation from PostgreSQL schemas with built-in semantic layer for LLM-powered analytics. Local-first, privacy-preserving.

## Features

✨ **Automated Data Modeling**: Extracts PostgreSQL schemas and generates production-ready dbt projects
🏗️ **Medallion Architecture**: Bronze (raw) → Silver (dimensional) → Gold (aggregated)
🤖 **LLM-Enhanced**: Uses local Ollama models for intelligent suggestions and validation
🔒 **Privacy-First**: All processing happens locally, no data leaves your machine
📊 **Semantic Layer**: Generates LLM-ready metadata for self-service analytics

## Install

```bash
pip install -e .
```

## Requirements

- Python 3.10+
- PostgreSQL database
- Ollama with `qwen-data:latest` or `qwen2.5-coder:7b`

## Quick Start

### One-Command Generation (Interactive)

```bash
schemalytics generate \
  --connection postgresql://user:pass@localhost/mydb \
  --output ./my_dbt_project \
  --name my_project

# You'll be prompted for:
# - Business type (ecommerce/saas/generic)
# - Primary entities
# - Analytical goals
# - Temporal tracking needs
# - Data grain preference

# Context is saved to context.yaml for future use
```

### Using Pre-Created Context

```bash
# Create context.yaml first
cat > context.yaml << EOF
business_type: ecommerce
entities: [customers, orders, products]
goals: [revenue_reporting, inventory_tracking]
temporal: historical
grain: transaction
EOF

# Then use it
schemalytics generate \
  --connection postgresql://user:pass@localhost/mydb \
  --context context.yaml \
  --output ./my_dbt_project
```

### Step-by-Step Workflow

```bash
# 1. Extract schema
schemalytics extract --connection postgresql://... --output schema.json

# 2. Create context file (or let generate command prompt you)
cat > context.yaml << EOF
business_type: ecommerce
entities: [customers, orders, products]
goals: [revenue_reporting, inventory_tracking]
temporal: historical
grain: transaction
EOF

# 3. Generate modeling plan (with LLM validation and Gold suggestions)
schemalytics plan --schema schema.json --context context.yaml --output plan.yaml

# 4. Build dbt project with semantic layer
schemalytics build \
  --schema schema.json \
  --plan plan.yaml \
  --context context.yaml \
  --output ./dbt_project
```

## Output Structure

```
dbt_project/
├── dbt_project.yml
├── semantic_layer.yml          # LLM-ready metadata
├── models/
│   ├── sources.yml
│   ├── bronze/                 # Raw passthrough (views)
│   ├── silver/
│   │   ├── dimensions/         # SCD1/SCD2 dimensions
│   │   └── facts/              # Fact tables
│   └── gold/                   # Pre-aggregated metrics
├── tests/
├── macros/
└── README.md
```

## Semantic Layer for LLM Analytics

The generated `semantic_layer.yml` provides:

- **Metric Definitions**: All available aggregations with descriptions
- **Dimensional Model**: Facts, dimensions, and their relationships  
- **Query Patterns**: Common analytical queries
- **LLM Guidelines**: How to query the data correctly

### Example LLM Usage

```python
# LLM can read semantic_layer.yml to understand:
# - Available metrics (daily_revenue, monthly_sales, etc.)
# - Time grains (daily, monthly, yearly)
# - Dimensions and their relationships
# - Pre-calculated aggregations in Gold layer

# Then generate accurate SQL:
SELECT 
  daily_date,
  total_revenue,
  order_count,
  avg_order_value
FROM gold_daily_sales_summary
WHERE daily_date >= CURRENT_DATE - 30
ORDER BY daily_date
```

## How It Works

1. **Schema Extraction**: SQLAlchemy inspects PostgreSQL structure
2. **Heuristic Classification**: FK graph analysis identifies facts vs dimensions
3. **LLM Validation**: Ollama validates classifications and suggests improvements
4. **Gold Generation**: LLM suggests common aggregate models based on business type
5. **Semantic Layer**: Metadata generation for LLM consumption
6. **Template Generation**: Jinja2 templates produce reliable, tested SQL

## Business Type Support

### E-commerce
- Metrics: `total_revenue`, `order_count`, `avg_order_value`, `customer_count`
- Grains: Daily, monthly, yearly sales aggregations

### SaaS
- Metrics: `active_users`, `mrr`, `arr`, `churn_rate`
- Grains: Daily/monthly user activity, retention cohorts

### Generic
- Metrics: `record_count`, activity aggregations
- Grains: Time-based rollups

## Architecture Decisions

**Why template-based SQL?**
- More reliable than pure LLM generation
- Guarantees syntactically correct SQL
- LLM fills parameters, doesn't write from scratch

**Why local LLM?**
- Privacy: No data sent to external APIs
- Cost: Zero API fees
- Control: Works offline, no rate limits

**Why Gold + Semantic Layer?**
- Performance: Pre-aggregated metrics
- LLM-ready: Structured metadata for accurate queries
- Self-service: Enables non-technical analytics

## Development

```bash
# Install in editable mode
pip install -e .

# Run tests
pytest

# Format code
ruff format .
```

## Roadmap

- [ ] Support additional databases (Snowflake, BigQuery, DuckDB)
- [ ] Web UI for interactive modeling
- [ ] Advanced SCD types (Type 3, Type 6)
- [ ] Data profiling and quality checks
- [ ] Custom business logic templates

## License

MIT