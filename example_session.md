# Interactive Refinement - Example Session

This document shows a complete example session using the new interactive refinement feature.

## Session: E-commerce Data Model Refinement

### Setup
```bash
$ schemalytics generate \
    --connection postgresql://localhost/ecommerce_db \
    --output ./ecommerce_dbt
```

---

## Iteration 1: Initial AI-Generated Plan

```
================================================================================
ITERATION 1
================================================================================

📦 BRONZE LAYER (Raw passthrough)
--------------------------------------------------------------------------------
  • bronze_customers
  • bronze_orders
  • bronze_order_items
  • bronze_products
  • bronze_categories
  • bronze_stores
  • bronze_employees
  • bronze_inventory
  • bronze_suppliers
  • bronze_shipments
  • bronze_reviews
  • bronze_carts
  • bronze_cart_items
  • bronze_payment_methods

Total: 14 tables (materialized as views)

================================================================================
🔷 SILVER LAYER - DIMENSIONS
================================================================================

dim_customers (SCD Type 2)
  Source: customers
  Grain: one row per customer per valid period
  Columns: customer_id, name, email, phone, address, city, state, 
           country, segment, status

dim_products (SCD Type 2)
  Source: products
  Grain: one row per product per valid period
  Columns: product_id, name, description, category_id, price, cost,
           stock_quantity, supplier_id

dim_categories (SCD Type 1)
  Source: categories
  Grain: one row per category
  Columns: category_id, name, parent_category_id, level

dim_stores (SCD Type 1)
  Source: stores
  Grain: one row per store
  Columns: store_id, name, address, city, state, country, manager_id

dim_employees (SCD Type 2)
  Source: employees
  Grain: one row per employee per valid period
  Columns: employee_id, name, email, position, department, hire_date,
           manager_id, store_id

dim_suppliers (SCD Type 1)
  Source: suppliers
  Grain: one row per supplier
  Columns: supplier_id, name, contact_name, email, phone, address

dim_payment_methods (SCD Type 1)
  Source: payment_methods
  Grain: one row per payment method
  Columns: payment_method_id, name, type, fee_percentage

Total: 7 dimension tables

================================================================================
📊 SILVER LAYER - FACTS
================================================================================

fct_orders
  Source: orders
  Grain: one row per order
  Date: order_date
  Foreign Keys:
    → customer_id → dim_customers
    → store_id → dim_stores
    → employee_id → dim_employees
  Measures: subtotal, tax_amount, shipping_cost, discount_amount, total_amount

fct_order_items
  Source: order_items
  Grain: one row per order line item
  Date: order_date
  Foreign Keys:
    → order_id → fct_orders
    → product_id → dim_products
  Measures: quantity, unit_price, line_total, discount

fct_reviews
  Source: reviews
  Grain: one row per product review
  Date: review_date
  Foreign Keys:
    → customer_id → dim_customers
    → product_id → dim_products
  Measures: rating, helpful_count

fct_shipments
  Source: shipments
  Grain: one row per shipment
  Date: ship_date
  Foreign Keys:
    → order_id → fct_orders
    → store_id → dim_stores
  Measures: shipping_cost, weight

Total: 4 fact tables

================================================================================
🥇 GOLD LAYER - PRE-AGGREGATED METRICS
================================================================================

DAILY AGGREGATES (4 tables):

  gold_daily_revenue
    Source: fct_orders
    Description: Daily revenue and order volume metrics
    Metrics:
      • total_revenue = SUM(total_amount)
      • order_count = COUNT(*)
      • avg_order_value = AVG(total_amount)
      • total_tax = SUM(tax_amount)

  gold_daily_product_sales
    Source: fct_order_items
    Description: Daily product sales performance
    Metrics:
      • units_sold = SUM(quantity)
      • revenue = SUM(line_total)
      • avg_unit_price = AVG(unit_price)

  gold_daily_customer_activity
    Source: fct_orders
    Description: Daily customer engagement metrics
    Metrics:
      • unique_customers = COUNT_DISTINCT(customer_id)
      • new_customers = COUNT_DISTINCT(CASE WHEN first_order THEN customer_id END)
      • repeat_customers = COUNT_DISTINCT(CASE WHEN NOT first_order THEN customer_id END)

  gold_daily_inventory_movement
    Source: fct_order_items
    Description: Daily inventory turnover
    Metrics:
      • items_sold = SUM(quantity)
      • revenue = SUM(line_total)

MONTHLY AGGREGATES (2 tables):

  gold_monthly_revenue
    Source: fct_orders
    Description: Monthly revenue trends and growth
    Metrics:
      • total_revenue = SUM(total_amount)
      • order_count = COUNT(*)
      • unique_customers = COUNT_DISTINCT(customer_id)
      • avg_order_value = AVG(total_amount)

  gold_monthly_product_performance
    Source: fct_order_items
    Description: Monthly product sales and trends
    Metrics:
      • units_sold = SUM(quantity)
      • revenue = SUM(line_total)
      • unique_products = COUNT_DISTINCT(product_id)

YEARLY AGGREGATES (1 table):

  gold_yearly_summary
    Source: fct_orders
    Description: Annual business performance summary
    Metrics:
      • total_revenue = SUM(total_amount)
      • order_count = COUNT(*)
      • unique_customers = COUNT_DISTINCT(customer_id)

================================================================================

================================================================================
FEEDBACK OPTIONS
================================================================================
  • Type natural language feedback to refine the plan
  • Examples:
    - 'make orders weekly instead of daily'
    - 'split customers into B2B and B2C dimensions'
    - 'add a metric for customer lifetime value'
    - 'remove the product dimension'
  • Type 'approve' or 'done' to accept the plan
  • Type 'reject' or 'cancel' to abort
================================================================================

Your feedback: _
```

---

## Iteration 2: User Refines Time Grains

**User Input:**
```
Your feedback: weekly aggregates are more useful than daily for our reporting
```

**LLM Processing:**
```
  🤖 Interpreting feedback and refining plan...
  ✓ Plan refined
```

**Changes Shown:**
```
================================================================================
CHANGES IN THIS ITERATION
================================================================================

  ✗ Removed gold aggregate: gold_daily_revenue
  ✗ Removed gold aggregate: gold_daily_product_sales
  ✗ Removed gold aggregate: gold_daily_customer_activity
  ✗ Removed gold aggregate: gold_daily_inventory_movement
  ✓ Added gold aggregate: gold_weekly_revenue
  ✓ Added gold aggregate: gold_weekly_product_sales
  ✓ Added gold aggregate: gold_weekly_customer_activity
  ✓ Added gold aggregate: gold_weekly_inventory_movement

================================================================================
```

**New Plan Excerpt:**
```
🥇 GOLD LAYER - PRE-AGGREGATED METRICS

WEEKLY AGGREGATES (4 tables):

  gold_weekly_revenue
    Source: fct_orders
    Description: Weekly revenue and order volume metrics
    Metrics:
      • total_revenue = SUM(total_amount)
      • order_count = COUNT(*)
      • avg_order_value = AVG(total_amount)
```

**Next Prompt:**
```
Your feedback: _
```

---

## Iteration 3: Split Customer Dimension

**User Input:**
```
Your feedback: we need to separate B2B and B2C customers into different dimensions
```

**Changes Shown:**
```
================================================================================
CHANGES IN THIS ITERATION
================================================================================

  ✗ Removed dimension: dim_customers
  ✓ Added dimension: dim_customers_b2b
  ✓ Added dimension: dim_customers_b2c
  ⟳ Modified fact: fct_orders (FK now points to both customer types)
  ⟳ Modified fact: fct_reviews (FK now points to both customer types)
  ⟳ Modified gold aggregate: gold_weekly_customer_activity (updated source)

================================================================================
```

**New Dimensions:**
```
dim_customers_b2b (SCD Type 2)
  Source: customers (WHERE customer_type = 'B2B')
  Grain: one row per B2B customer per valid period
  Columns: customer_id, company_name, contact_name, email, phone, address,
           account_manager_id, credit_limit, payment_terms

dim_customers_b2c (SCD Type 2)
  Source: customers (WHERE customer_type = 'B2C')
  Grain: one row per B2C customer per valid period
  Columns: customer_id, first_name, last_name, email, phone, address,
           loyalty_tier, birth_date
```

**Next Prompt:**
```
Your feedback: _
```

---

## Iteration 4: Add Custom Metric

**User Input:**
```
Your feedback: add a gold table for customer lifetime value calculation
```

**Changes Shown:**
```
================================================================================
CHANGES IN THIS ITERATION
================================================================================

  ✓ Added gold aggregate: gold_customer_lifetime_value

================================================================================
```

**New Gold Table:**
```
gold_customer_lifetime_value
  Source: fct_orders
  Description: Customer lifetime value metrics
  Metrics:
    • lifetime_revenue = SUM(total_amount)
    • order_count = COUNT(*)
    • first_order_date = MIN(order_date)
    • last_order_date = MAX(order_date)
    • customer_tenure_days = DATEDIFF(MAX(order_date), MIN(order_date))
    • avg_order_value = AVG(total_amount)
```

**Next Prompt:**
```
Your feedback: _
```

---

## Iteration 5: Remove Unnecessary Table

**User Input:**
```
Your feedback: we don't track shipments separately, remove that fact table
```

**Changes Shown:**
```
================================================================================
CHANGES IN THIS ITERATION
================================================================================

  ✗ Removed fact: fct_shipments
  ✗ Removed bronze table: bronze_shipments

================================================================================
```

**Next Prompt:**
```
Your feedback: _
```

---

## Iteration 6: Final Approval

**User Input:**
```
Your feedback: approve
```

**Output:**
```
✓ Plan approved! Generating dbt project...

🏗️  STEP 5: GENERATING DBT PROJECT
--------------------------------------------------------------------------------
  ✓ Created dbt_project.yml
  ✓ Created sources.yml
  ✓ Generated 13 bronze models
  ✓ Generated 8 silver dimension models
  ✓ Generated 3 silver fact models
  ✓ Generated 8 gold aggregate models
  ✓ Created semantic layer (542 lines)
  ✓ Generated comprehensive documentation

================================================================================
✅ SUCCESS!
================================================================================

Project created at: ./ecommerce_dbt

Contents:
  • 13 bronze models (raw passthrough)
  • 8 silver dimensions
  • 3 silver facts
  • 8 gold aggregates

Semantic layer: ./ecommerce_dbt/semantic_layer.yml

Next steps:
  1. cd ./ecommerce_dbt
  2. Configure profiles.yml with your database connection
  3. dbt deps  # Install dependencies
  4. dbt run   # Build all models

================================================================================
```

---

## Summary of Changes Through Iterations

| Iteration | User Feedback | Changes |
|-----------|--------------|---------|
| 1 | Initial plan | 14 bronze, 7 dims, 4 facts, 7 gold |
| 2 | "weekly aggregates more useful" | Changed 4 daily → weekly |
| 3 | "separate B2B and B2C customers" | Split 1 dim → 2 dims |
| 4 | "add customer lifetime value" | Added 1 gold table |
| 5 | "remove shipments" | Removed 1 fact, 1 bronze |
| 6 | "approve" | Final: 13 bronze, 8 dims, 3 facts, 8 gold |

## Key Features Demonstrated

1. ✅ **Concrete Specifications** - Exact table names, columns, FKs visible
2. ✅ **Natural Language** - Casual phrasing works ("more useful", "we need")
3. ✅ **Iterative Refinement** - Multiple rounds of feedback
4. ✅ **Change Tracking** - Clear diff after each iteration
5. ✅ **Complex Changes** - Splitting dimensions, adding metrics, removing tables
6. ✅ **No Limit** - Unlimited iterations until user approves

## Alternative Feedback Examples

### More Ways to Express Changes

**Change grain:**
- "make it daily"
- "weekly is better"
- "aggregate by month"
- "change revenue to monthly grain"

**Add tables:**
- "add a metric for churn rate"
- "we need inventory forecasting"
- "create a gold table for cohort analysis"

**Remove tables:**
- "drop the reviews dimension"
- "we don't need employee tracking"
- "remove all yearly aggregates"

**Modify structure:**
- "orders should track refunds as a measure"
- "add supplier info to products"
- "change customers to SCD Type 1"

**Validation failures:**
```
Your feedback: make products a fact table

  ⚠️  Validation issue: Products cannot be a fact table because they have 
      multiple incoming foreign keys (referenced by order_items, reviews, 
      inventory). Facts typically reference dimensions, not vice versa.
      
      Would you like to:
      1. Keep dim_products as a dimension
      2. Create a separate fct_product_events table for product-level transactions
      
  Please clarify your feedback or type 'skip' to keep current plan.
```

The validation ensures users understand why certain changes don't make sense, and suggests alternatives.