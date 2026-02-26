# Interactive Refinement

The interactive refinement loop is the core of the Schemalytics workflow. Instead of generating a dbt project in one shot and hoping it's right, Schemalytics shows you exactly what it will build — and lets you adjust it through natural language until it's exactly what you want.

---

## How It Works

```
LLM generates detailed plan
         ↓
Display concrete plan (tables, columns, FKs, metrics)
         ↓
You give feedback (natural language)  ←──────────────┐
         ↓                                            │
LLM interprets and refines plan                       │
         ↓                                            │
Show diff of changes                                  │
         ↓                                            │
Approved? ──NO────────────────────────────────────────┘
         ↓
        YES
         ↓
Generate dbt project
```

Each iteration is independent and stateless — the LLM always receives the full current plan, so there's no drift over multiple rounds.

---

## The Refinement Prompt

After each plan display, you'll see:

```
================================================================================
FEEDBACK OPTIONS
================================================================================
  • Type natural language feedback to refine the plan
  • Type 'approve' or 'done' to accept the plan
  • Type 'reject' or 'cancel' to abort

Your feedback: _
```

---

## Control Commands

| Input | Action |
|-------|--------|
| `approve` | Accept the current plan and generate the dbt project |
| `done` | Same as `approve` |
| `reject` | Abort — no files are written |
| `cancel` | Same as `reject` |
| Any other text | Treated as natural language feedback for refinement |

---

## Feedback Examples

### Change time grain

```
"make revenue weekly instead of daily"
"change to monthly aggregates"
"daily is too granular, use weekly"
"aggregate by month for the gold layer"
```

### Add tables or metrics

```
"add a customer lifetime value calculation"
"we need a churn rate metric"
"create a gold table for cohort analysis"
"add monthly product performance"
```

### Remove tables

```
"drop the shipments fact table"
"we don't track inventory separately, remove it"
"remove all yearly aggregates"
"delete the suppliers dimension"
```

### Split or combine

```
"split customers into B2B and B2C dimensions"
"combine products and categories into one dimension"
"separate orders by channel"
```

### Modify attributes

```
"add discount as a measure to fct_orders"
"change customers to SCD Type 1, we don't need history"
"include tax in the revenue measure"
"track refunds as a separate measure"
```

---

## Understanding the Plan Display

### Bronze layer

```
📦 BRONZE LAYER (Raw passthrough)
  • stg_public_customers
  • stg_public_orders
  • stg_public_products
```

Naming: `stg_<schema>_<table>`. These are views that pass through raw data unchanged.

### Silver dimensions

```
🔷 SILVER LAYER - DIMENSIONS

dim_customers (SCD Type 2)
  Source: customers
  Grain: one row per customer per valid period
  Columns: customer_id, company_name, email, city, country, status
```

- **SCD Type 1** — overwrites previous values (no history)
- **SCD Type 2** — adds a new row on change, keeps full history

### Silver facts

```
📊 SILVER LAYER - FACTS

fct_orders
  Source: orders
  Grain: one row per order
  Date: order_date
  Foreign Keys:
    → customer_id → dim_customers
    → product_id → dim_products
  Measures: total_amount, discount, tax
```

### Gold aggregates

```
🥇 GOLD LAYER - PRE-AGGREGATED METRICS

agg_monthly_revenue
  Source: fct_orders
  Description: Monthly revenue and order metrics
  Metrics:
    • total_revenue = SUM(total_amount)
    • order_count = COUNT(*)
    • avg_order_value = AVG(total_amount)
```

Naming: `agg_<grain>_<metric>`.

---

## Understanding the Diff

After each refinement, you see exactly what changed:

```
================================================================================
CHANGES IN THIS ITERATION
================================================================================

  ✗ Removed gold aggregate: agg_daily_revenue
  ✓ Added gold aggregate: agg_weekly_revenue
  ⟳ Modified fact: fct_orders (added measure: tax_amount)
  ✓ Added dimension: dim_customers_b2b
  ✓ Added dimension: dim_customers_b2c
  ✗ Removed dimension: dim_customers

================================================================================
```

| Symbol | Meaning |
|--------|---------|
| `✓` | Added |
| `✗` | Removed |
| `⟳` | Modified |

---

## Tips

**Be specific, not vague**

| Less effective | More effective |
|----------------|----------------|
| "make it better" | "change the gold revenue tables to weekly grain" |
| "fix customers" | "change dim_customers to SCD Type 1" |
| "add more metrics" | "add avg_order_value and unique_customers to agg_monthly_revenue" |

**Casual phrasing works fine**

The LLM understands natural speech. These all mean the same thing:
- "make revenue weekly"
- "weekly is better for us"
- "change to weekly aggregates"
- "weekly revenue instead of daily"

**Undo with opposite feedback**

If you remove something by mistake:
```
Your feedback: drop the products dimension
...
Your feedback: actually add back dim_products
```

**No iteration limit**

Take as many rounds as needed. Each iteration only takes a few seconds.

---

## Full Example Session

See [example_session.md](../../example_session.md) for a complete 6-iteration walkthrough on an e-commerce database, demonstrating grain changes, dimension splits, adding custom metrics, and removing unused tables.
