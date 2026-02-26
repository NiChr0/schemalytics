# Getting Started

This guide walks through a complete first run against the Northwind sample database.

---

## Step 1: Start prerequisites

```bash
# Start Ollama (if not already running)
ollama serve

# Start the test database (optional — use your own PostgreSQL instead)
docker run -d \
  -p 5432:5432 \
  -e POSTGRES_PASSWORD=postgres \
  ghcr.io/nichr0/northwind-postgres:latest
```

---

## Step 2: Run Schemalytics

```bash
schemalytics generate \
  -c postgresql://postgres:postgres@localhost:5432/northwind \
  -o ./northwind_dbt \
  -n northwind
```

---

## Step 3: Answer the context prompts

Schemalytics will ask about your business context interactively:

```
Select industry:
  1. E-commerce & Retail
  2. SaaS & Software
  3. Finance & Fintech
  ...
> 1

Key business entities (comma-separated):
> customers, orders, products

Analytical goals (comma-separated):
> revenue tracking, customer analysis, product performance

Temporal tracking strategy:
  1. historical_tracking (SCD Type 2 — keeps full history)
  2. current_only (SCD Type 1 — overwrites)
> 1

Primary time grain:
  1. transaction_level
  2. daily
  3. weekly
> 1
```

**Tip:** You can skip interactive prompts by passing a context file with `-x`. See [Configuration](Configuration).

---

## Step 4: Review and refine the plan

Schemalytics generates an initial plan and displays it:

```
================================================================================
ITERATION 1
================================================================================

📦 BRONZE LAYER (Raw passthrough)
  • stg_public_customers
  • stg_public_orders
  • stg_public_products
  • stg_public_order_details
  ...

🔷 SILVER LAYER - DIMENSIONS
  dim_customers (SCD Type 2)
    Source: customers
    Grain: one row per customer per valid period
    Columns: customer_id, company_name, contact_name, city, country

  dim_products (SCD Type 2)
    Source: products
    Grain: one row per product per valid period
    Columns: product_id, product_name, category_id, unit_price

📊 SILVER LAYER - FACTS
  fct_orders
    Source: orders
    Grain: one row per order
    Date: order_date
    Foreign Keys:
      → customer_id → dim_customers
    Measures: freight

🥇 GOLD LAYER - PRE-AGGREGATED METRICS
  agg_daily_revenue
    Metrics: total_revenue = SUM(freight), order_count = COUNT(*)

================================================================================
Your feedback:
```

Type your feedback or `approve`:

```
Your feedback: make revenue monthly instead of daily, and add order item metrics

Changes:
  ✗ Removed gold aggregate: agg_daily_revenue
  ✓ Added gold aggregate: agg_monthly_revenue
  ✓ Added fact: fct_order_details

Your feedback: approve
```

---

## Step 5: Output generated

```
✓ Plan approved! Generating dbt project...

  ✓ Created dbt_project.yml
  ✓ Created sources.yml
  ✓ Generated 8 bronze models
  ✓ Generated 4 silver dimension models
  ✓ Generated 2 silver fact models
  ✓ Generated 3 gold aggregate models
  ✓ Created semantic layer
  ✓ Generated documentation

Project created at: ./northwind_dbt
```

---

## Step 6: Run the dbt project

```bash
cd northwind_dbt

# Configure your database connection
# Edit profiles.yml or set DBT_PROFILES_DIR

dbt run
dbt test
```

---

## What's in the output?

```
northwind_dbt/
├── dbt_project.yml
├── semantic_layer.yml          ← LLM-ready metadata
├── README.md
└── models/
    ├── sources.yml
    ├── bronze/                 ← Raw views
    ├── silver/
    │   ├── dimensions/         ← dim_* tables
    │   └── facts/              ← fct_* tables
    └── gold/                   ← agg_* aggregates
```

See [Output Structure](Output-Structure) for full details.

---

## Next Steps

- [Interactive Refinement](Interactive-Refinement) — Master the refinement loop
- [CLI Reference](CLI-Reference) — All options and flags
- [Configuration](Configuration) — Skip interactive prompts with a context file
- [Semantic Layer](Semantic-Layer) — Use the generated metadata for LLM-assisted analytics
