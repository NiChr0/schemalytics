# DataForge

Automated dbt project generation from PostgreSQL schemas. Local-first, privacy-preserving.

## Install

```bash
pip install -e .
```

## Requirements

- Python 3.10+
- PostgreSQL database
- Ollama with `qwen2.5-coder:7b` (optional, for LLM enhancement)

## Usage

### One-shot generation

```bash
schemalytics generate \
  --connection postgresql://user:pass@localhost/mydb \
  --output ./my_dbt_project \
  --name my_project
```

### Step-by-step

```bash
# 1. Extract schema
schemalytics extract --connection postgresql://... --output schema.json

# 2. Create context file
cat > context.yaml << EOF
business_type: ecommerce
entities: [customers, orders, products]
goals: [revenue_reporting, inventory_tracking]
temporal: historical
grain: transaction
EOF

# 3. Generate plan
schemalytics plan --schema schema.json --context context.yaml --output plan.yaml

# 4. Build project
schemalytics build --schema schema.json --plan plan.yaml --output ./dbt_project
```

## Output Structure

```
dbt_project/
├── dbt_project.yml
├── models/
│   ├── sources.yml
│   ├── bronze/          # Raw passthrough
│   ├── silver/
│   │   ├── dimensions/  # Dim tables (SCD1/SCD2)
│   │   └── facts/       # Fact tables
│   └── gold/            # Aggregates (TODO)
├── tests/
├── macros/
└── README.md
```

## How It Works

1. **Schema Extraction**: SQLAlchemy inspects your Postgres DB
2. **Heuristics**: Pattern matching identifies facts vs dimensions
3. **LLM Enhancement**: Optional Ollama-powered suggestions
4. **Template Generation**: Jinja2 templates (not pure LLM) for reliable SQL

## License

MIT
