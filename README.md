# Schemalytics

**Automated dbt project generation from PostgreSQL schemas with comprehensive semantic layer for LLM-powered analytics.**

Schemalytics extracts your PostgreSQL database schema, intelligently classifies tables as facts or dimensions using AI-powered analysis, and generates a production-ready dbt project with medallion architecture (Bronze → Silver → Gold). The tool creates a detailed semantic layer that enables LLMs to understand your data model and generate accurate SQL queries for self-service analytics.

## Key Features

✨ **Automated Data Modeling** - Extracts schemas and generates dbt projects automatically  
🏗️ **Medallion Architecture** - Bronze (raw) → Silver (dimensional) → Gold (aggregated)  
🤖 **AI-Enhanced Classification** - Uses local LLMs (Ollama) to validate table classifications  
🔒 **Privacy-First** - All processing happens locally, no data leaves your machine  
📊 **Comprehensive Semantic Layer** - 500+ lines of LLM-ready metadata for accurate queries  
📝 **Complete dbt Documentation** - Auto-generated schema.yml files with tests and descriptions  
🎯 **Industry Templates** - 50+ pre-configured industry patterns (E-commerce, SaaS, Finance, etc.)

## Installation

### Prerequisites

- **Python 3.10+**
- **PostgreSQL database** (with data to model)
- **Ollama** with AI models for intelligent classification

### 1. Install Ollama & Models

```bash
# Install Ollama (https://ollama.ai)
# macOS/Linux:
curl -fsSL https://ollama.com/install.sh | sh

# Pull required models
ollama pull qwen-data:latest
ollama pull qwen2.5-coder:7b  # Fallback model
```

### 2. Install Schemalytics

```bash
# Clone the repository
git clone https://github.com/yourusername/schemalytics.git
cd schemalytics

# Install in development mode
pip install -e .
```

### 3. Verify Installation

```bash
# Check if schemalytics is installed
schemalytics --version

# Verify Ollama is running
ollama list
```

## Quick Start

### One-Command Generation (Interactive)

```bash
schemalytics generate \
  --connection postgresql://user:password@localhost:5432/mydb \
  --output ./my_dbt_project \
  --name my_project
```

**You'll be prompted for:**
1. **Industry** - Select from 14 main industries (E-commerce, SaaS, Finance, etc.)
2. **Sub-industry** - Choose specific business type (B2C, B2B, Marketplace, etc.)
3. **Entities** - Review and edit suggested entities (customers, orders, products)
4. **Goals** - Review and edit analytical goals (revenue_reporting, customer_ltv)
5. **Temporal Tracking** - Choose SCD type (snapshot, historical, or both)
6. **Time Grains** - Select Gold layer aggregations (daily, weekly, monthly, yearly)

The tool will:
- Extract your database schema (14 tables in ~2 seconds)
- Classify tables as facts/dimensions using AI (5 facts, 9 dimensions)
- Generate Gold layer aggregates based on your selections
- Create a complete dbt project with semantic layer

### Using Pre-Created Context

```bash
# Create context.yaml
cat > context.yaml << EOF
business_type: ecommerce_retail_b2c
entities: [customers, orders, products, order_items]
goals: [revenue_reporting, customer_lifetime_value, inventory_tracking]
temporal: historical
grain: daily,weekly,monthly
EOF

# Generate with context file
schemalytics generate \
  --connection postgresql://user:password@localhost:5432/mydb \
  --context context.yaml \
  --output ./my_dbt_project
```

### Step-by-Step Workflow

```bash
# 1. Extract schema
schemalytics extract \
  --connection postgresql://user:password@localhost:5432/mydb \
  --output schema.json

# 2. Generate modeling plan (with AI validation)
schemalytics plan \
  --schema schema.json \
  --context context.yaml \
  --output plan.yaml

# 3. Build dbt project
schemalytics build \
  --schema schema.json \
  --plan plan.yaml \
  --context context.yaml \
  --output ./dbt_project
```

## Generated Project Structure

```
dbt_project/
├── dbt_project.yml                 # dbt project configuration
├── semantic_layer.yml              # Comprehensive LLM-ready metadata (500+ lines)
├── models/
│   ├── sources.yml                 # Source definitions
│   ├── bronze/                     # Raw passthrough (views)
│   │   ├── schema.yml              # Bronze documentation
│   │   └── bronze_*.sql
│   ├── silver/
│   │   ├── dimensions/             # SCD1/SCD2 dimensions
│   │   │   ├── schema.yml          # Dimension documentation with tests
│   │   │   └── dim_*.sql
│   │   └── facts/                  # Fact tables
│   │       ├── schema.yml          # Fact documentation with tests
│   │       └── fct_*.sql
│   └── gold/                       # Pre-aggregated metrics
│       ├── schema.yml              # Metrics documentation
│       └── gold_*.sql
├── tests/
├── macros/
└── README.md
```

## Semantic Layer for LLM Analytics

The generated `semantic_layer.yml` provides comprehensive metadata including:

### Metrics Catalog
- SQL formulas and aggregation types
- Use cases and example queries
- Data types and null handling rules
- Common filters and time ranges

### Dimensional Model
- Complete fact and dimension documentation
- Grain definitions and relationships
- Join patterns and cardinality
- SCD type information

### Query Guidelines
- Query strategy (Gold → Silver → Bronze)
- Performance optimization tips
- Common mistakes and solutions
- Date and null handling rules

### Query Library
- Pre-built analytical queries
- Period-over-period comparisons
- Cross-fact analysis patterns

### Example LLM Usage

An LLM can read `semantic_layer.yml` to understand:
- Available metrics (daily_revenue, monthly_sales, customer_ltv)
- Time grains (daily, weekly, monthly, yearly)
- Dimension relationships and join paths
- Pre-calculated aggregations in Gold layer

Then generate accurate SQL:
```sql
-- LLM understands to query Gold layer first
SELECT 
  daily_date,
  total_revenue,
  order_count,
  avg_order_value
FROM gold_daily_revenue
WHERE daily_date >= CURRENT_DATE - 30
ORDER BY daily_date DESC
```

## How It Works

### 1. Schema Extraction
SQLAlchemy inspects your PostgreSQL database and extracts:
- Tables, columns, and data types
- Primary keys and foreign keys
- Relationships and constraints

### 2. Intelligent Classification
**Heuristic Analysis:**
- FK graph analysis identifies patterns
- Tables with many outgoing FKs → Facts
- Tables with many incoming FKs → Dimensions

**AI Validation:**
- Local LLM (Ollama) validates classifications
- Provides reasoning for each decision
- Suggests corrections for ambiguous cases

### 3. Interactive Review
- User reviews proposed model
- Can edit table classifications
- Accepts or rejects plan before generation

### 4. Gold Layer Generation
**AI-Powered Metrics:**
- LLM suggests common aggregations based on industry
- Generates metrics aligned with analytical goals

**Heuristic Fallback:**
- Time-based aggregates (daily, weekly, monthly, yearly)
- Business-specific patterns (e-commerce, SaaS metrics)

### 5. Template-Based SQL Generation
- Jinja2 templates ensure syntactically correct SQL
- LLM fills parameters, doesn't write SQL from scratch
- Guarantees production-ready, tested code

## Industry Support

### Available Industries (14 Main Categories)

1. **E-commerce & Retail** - B2C, B2B, Marketplace, Subscription
2. **SaaS & Software** - B2B, B2C, Platform, Collaboration
3. **Finance & Fintech** - Banking, Payments, Lending, Investment, Crypto, Insurance
4. **Healthcare** - Provider, Telehealth, Pharmacy, Health Apps
5. **Media & Entertainment** - Streaming, Gaming, Social Media, Publishing
6. **Marketing & Advertising** - Automation, Ad Networks, Email, Influencer
7. **Education** - K-12, Higher Ed, Online Courses, Corporate Training
8. **Logistics & Transportation** - Shipping, Warehouse, Rideshare, Delivery
9. **Hospitality & Travel** - Hotels, Booking, Restaurants, Vacation Rentals
10. **Real Estate** - Residential, Commercial, Property Management
11. **Manufacturing** - Production, Supply Chain, Inventory
12. **Human Resources** - HRIS, Recruiting, Payroll, Talent Marketplaces
13. **Nonprofit & Government** - Fundraising, Public Services
14. **Other/Custom** - Generic business patterns

Each industry includes:
- Pre-configured entities
- Analytical goals
- Common metrics
- Best practices

## Architecture Decisions

### Why Local LLM?
- **Privacy** - No data sent to external APIs
- **Cost** - Zero API fees
- **Control** - Works offline, no rate limits
- **Speed** - Optimized for consumer hardware (8GB RAM MacBook)

### Why Template-Based SQL?
- **Reliability** - Guarantees syntactically correct SQL
- **Consistency** - Follows dbt best practices
- **Maintainability** - Easy to update and extend
- **Quality** - Production-tested patterns

### Why Gold + Semantic Layer?
- **Performance** - Pre-aggregated metrics (10-100x faster)
- **LLM-Ready** - Structured metadata for accurate queries
- **Self-Service** - Enables non-technical analytics
- **Scalability** - Reduces query complexity

## Configuration

### Connection String Format

```bash
postgresql://username:password@hostname:port/database

# Examples:
postgresql://postgres:mypassword@localhost:5432/mydb
postgresql://user@localhost/mydb  # No password
postgresql://user:pass@remote.host:5432/db
```

### Context File Options

```yaml
business_type: ecommerce_retail_b2c  # Industry_subindustry format
entities:
  - customers
  - orders
  - products
goals:
  - revenue_reporting
  - customer_lifetime_value
  - inventory_tracking
temporal: historical  # snapshot | historical | both
grain: daily,weekly,monthly  # Comma-separated time grains
```

## Development

```bash
# Install in editable mode with dev dependencies
pip install -e ".[dev]"

# Run tests
pytest

# Format code
ruff format .

# Type checking
mypy schemalytics
```

## Troubleshooting

### Ollama Not Running
```bash
# Check if Ollama is running
curl http://localhost:11434/api/tags

# Start Ollama
ollama serve
```

### Database Connection Issues
```bash
# Test connection with psql
psql postgresql://user:pass@localhost:5432/mydb

# Check if database exists
psql -U postgres -l
```

### Model Not Found
```bash
# List available models
ollama list

# Pull required model
ollama pull qwen-data:latest
```

### Timeout Issues
Default LLM timeout is 15 minutes. For large schemas, this may need adjustment in `llm.py`:
```python
LLM_TIMEOUT = 900.0  # Increase if needed
```

## Roadmap

- [ ] Support additional databases (Snowflake, BigQuery, DuckDB)
- [ ] Web UI for interactive modeling
- [ ] Advanced SCD types (Type 3, Type 6)
- [ ] Data profiling and quality checks
- [ ] Custom business logic templates
- [ ] dbt Cloud integration
- [ ] Incremental model generation
- [ ] Multi-tenant support

## Contributing

Contributions welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Add tests for new functionality
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Support

- **Issues**: [GitHub Issues](https://github.com/yourusername/schemalytics/issues)
- **Documentation**: See `semantic_layer.yml` in generated projects
- **Examples**: Check the `examples/` directory

## Credits

Built with:
- [SQLAlchemy](https://www.sqlalchemy.org/) - Database inspection
- [Ollama](https://ollama.ai/) - Local LLM inference
- [Jinja2](https://jinja.palletsprojects.com/) - SQL templating
- [Click](https://click.palletsprojects.com/) - CLI framework
- [Pydantic](https://docs.pydantic.dev/) - Data validation

---

**Schemalytics** - Transform your database into an LLM-ready analytics platform in minutes.