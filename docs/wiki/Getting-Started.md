# Getting Started

This guide walks through a complete first run of Schemalytics against a PostgreSQL database.

---

## Step 1: Start prerequisites

```bash
# Start Ollama (if not already running)
ollama serve
```

Have a PostgreSQL connection string ready — point it at any database you have access to.

---

## Step 2: Run Schemalytics

```bash
schemalytics generate \
  -c postgresql://user:password@localhost:5432/mydb \
  -o ./my_dbt_project \
  -n my_project
```

---

## Step 3: Watch the agents work

Schemalytics runs five agents automatically, showing their reasoning as they go:

```
[Agent 1] Inferring industry...
  → Industry: Retail / Wholesale Distribution (confidence: 3)

[Agent 2] Suggesting metrics...
  → Metrics: total_revenue, order_count, avg_order_value, ...

[Agent 3] Classifying 13 tables...
  → orders: fact (confidence: 3)
  → customers: dimension (confidence: 3)
  → products: dimension (confidence: 3)
  → ...

──────────────────────────── PIPELINE SUMMARY ────────────────────────────
Industry:    Retail — Wholesale Distribution
Metrics:     total_revenue, order_count, avg_order_value
Goals:       revenue_reporting, customer_analysis, product_performance
Grain:       order_line
Table roles: facts=[orders, order_details]  dims=[customers, products, ...]

Press Enter to continue, or describe any corrections:
```

Review the summary and press Enter to proceed, or type corrections in plain English.

---

## Step 4: Review and refine the plan

Agent 4 generates the modeling plan and displays it:

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
  dim_customers (SCD Type 1)
    Source: customers
    Grain: one row per customer

  dim_products (SCD Type 1)
    Source: products
    Grain: one row per product

📊 SILVER LAYER - FACTS
  fct_order_details
    Source: order_details
    Grain: one row per order line
    Date: order_date
    Measures: unit_price, quantity, discount
    Derived: line_total = unitprice * quantity * (1 - discount)

🥇 GOLD LAYER - PRE-AGGREGATED METRICS
  agg_monthly_revenue
    Metrics: total_revenue = SUM(line_total), order_count = COUNT(*)

================================================================================
Your feedback (or press Enter to approve):
```

Type feedback or press Enter to approve:

```
Your feedback: make freight a measure on fct_orders too

Changes:
  ~ Modified fct_orders (added freight to measures)

Your feedback:   ← (press Enter to approve)
```

---

## Step 5: Output generated

```
✓ Plan approved! Generating dbt project...

  ✓ Created dbt_project.yml
  ✓ Created sources.yml
  ✓ Generated 13 bronze models
  ✓ Generated 4 silver dimension models
  ✓ Generated 2 silver fact models
  ✓ Generated 2 gold aggregate models
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

dbt deps   # install dbt-utils
dbt run
dbt test
```

---

## What's in the output?

```
northwind_dbt/
├── dbt_project.yml
├── packages.yml                ← dbt-utils dependency
├── semantic_layer.yml          ← LLM-ready metadata
├── README.md
└── models/
    ├── sources.yml
    ├── bronze/                 ← Raw views (stg_*)
    ├── silver/
    │   ├── dimensions/         ← dim_* tables (SCD1 or SCD2)
    │   └── facts/              ← fct_* tables (incremental)
    └── gold/                   ← agg_* aggregates
```

---

## Next Steps

- [CLI Reference](CLI-Reference) — All options and flags
- [Architecture](Architecture) — How the pipeline works internally
- [Troubleshooting](Troubleshooting) — Common issues and fixes
