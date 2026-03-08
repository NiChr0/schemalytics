# Example Session

A complete walkthrough of `schemalytics generate` against the Northwind database.

```bash
schemalytics generate \
  -c postgresql://postgres:mypassword@localhost/northwind \
  -o ./northwind_dbt
```

---

## Step 1 — Schema extraction

```
SCHEMALYTICS — AGENTIC DATA MODEL GENERATION
================================================================

Extracting database schema...
  Found 13 tables
```

---

## Step 2 — Agent 1: Industry inference

```
Agent 1 — Inferring industry and domain...
  Detected: retail (wholesale_distribution)
  Reasoning: Schema has customers, orders, order_details, products, suppliers,
             and employees tables — a classic wholesale distribution pattern.
```

Confidence 3 → auto-proceeds.

---

## Step 3 — Agent 2: Metrics + goals

```
Agent 2 — Suggesting metrics and goals...
  Detected: metrics=['total_revenue', 'order_count', 'avg_order_value',
            'units_sold', 'freight_cost'] grain=order_line
  Reasoning: orders.freight and order_details.unit_price/quantity/discount
             enable revenue and volume metrics at order-line grain.
```

Confidence 3 → auto-proceeds.

---

## Step 4 — Agent 3: Table classification

```
Agent 3 — Classifying tables...
  The following tables have uncertain classifications:
    territories: dimension (confidence=1) — No FKs in or out; purpose unclear from name alone.

  Correct any table roles in plain English (or press Enter to accept): territories is a lookup table for sales regions, treat it as reference
  Re-running Agent 3 with your corrections...
  All table classifications are high-confidence.
```

---

## Step 5 — Summary gate (always runs)

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
INFERRED CONTEXT — please review
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Industry:     retail (wholesale_distribution)
Key metrics:  total_revenue, order_count, avg_order_value, units_sold, freight_cost
Goals:        revenue_reporting, supplier_performance, customer_order_analysis
Grain:        order_line

Table roles:
  facts:       order_details, orders
  dimensions:  customers, employees, products, categories, suppliers, shippers
  bridge:      employee_territories
  reference:   territories, region

Anything wrong? Enter corrections or press Enter to continue:
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

User presses Enter → proceeds.

---

## Step 6 — Agent 4: Modeling plan

```
Agent 4 — Generating modeling plan...

================================================================
MODELING PLAN
================================================================

Bronze (13 tables):
  stg_public_categories
  stg_public_customers
  stg_public_employee_territories
  stg_public_employees
  stg_public_order_details
  stg_public_orders
  stg_public_products
  stg_public_region
  stg_public_shippers
  stg_public_suppliers
  stg_public_territories
  stg_public_us_states
  stg_public_customer_customer_demo

Silver Dimensions (6):
  dim_customers  [SCD2]  source=customers  grain=one row per customer per version
  dim_employees  [SCD2]  source=employees  grain=one row per employee per version
  dim_products   [SCD2]  source=products   grain=one row per product per version
  dim_categories [SCD1]  source=categories grain=one row per category
  dim_suppliers  [SCD1]  source=suppliers  grain=one row per supplier
  dim_shippers   [SCD1]  source=shippers   grain=one row per shipper

Silver Facts (2):
  fct_orders       source=orders        grain=one row per order       date=order_date  measures=[freight]
  fct_order_lines  source=order_details grain=one row per order line  date=order_date  measures=[unit_price, quantity, discount]

Gold (3):
  agg_daily_revenue    [daily]   source=fct_order_lines  metrics=[total_revenue, order_count, units_sold]
  agg_monthly_revenue  [monthly] source=fct_order_lines  metrics=[total_revenue, avg_order_value]
  agg_supplier_sales   [monthly] source=fct_order_lines  metrics=[total_revenue, units_sold]
================================================================

Type natural language feedback to refine the plan, or press Enter to approve.
Feedback: _
```

---

## Step 7 — Refinement (Agent 5)

**User:** `add a gold table for freight cost by shipper, daily`

```
  Agent 5 — Applying feedback...

Changes:
  + Added agg_daily_freight_by_shipper

================================================================
MODELING PLAN
...
Gold (4):
  agg_daily_revenue          [daily]   ...
  agg_monthly_revenue        [monthly] ...
  agg_supplier_sales         [monthly] ...
  agg_daily_freight_by_shipper [daily] source=fct_orders  metrics=[total_freight, shipment_count]
================================================================

Feedback: _
```

**User:** *(presses Enter)*

```
Plan approved. Proceeding to generation...
```

---

## Step 8 — dbt project generation

```
Generating dbt project...

================================================================
SUCCESS
================================================================

Project created at: ./northwind_dbt
  13 bronze models
  6 silver dimensions
  2 silver facts
  4 gold aggregates

Next steps:
  cd ./northwind_dbt
  dbt deps
  dbt run
```

---

## Refinement feedback examples

### Change grain
```
"aggregate orders monthly, not daily"
"weekly is better for our reporting cadence"
```

### Add tables / metrics
```
"add customer lifetime value as a gold aggregate"
"we need a fact table for order returns"
"add units_returned as a measure to fct_order_lines"
```

### Remove tables
```
"drop the agg_supplier_sales table, we don't need it"
"remove us_states from bronze — it's not used"
```

### Reclassify
```
"employee_territories should be a bridge table, not dimension"
"region is a dimension, not reference"
```

### Complex changes
```
"split dim_customers into dim_customers_us and dim_customers_international based on country"
"change fct_orders to SCD2"
"move freight from fct_orders to fct_order_lines"
```

### Cancel
```
cancel
```
