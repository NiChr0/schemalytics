# Interactive Refinement Loop - Integration Guide

## Overview

The new interactive refinement loop transforms Schemalytics from a one-shot generator into an **iterative, collaborative tool** where users can refine the data model through natural language feedback until it's exactly right.

## What Changed

### Before (v0.1.0)
```
Extract → Heuristic Classification → User reviews → Accept/Edit/Reject → Generate
                                     ↑
                                  Vague display
                                  Manual edits only
                                  No LLM help
```

### After (v0.2.0)
```
Extract → Heuristic Classification → LLM generates DETAILED plan
                                               ↓
                                    Display CONCRETE plan
                                               ↓
                                    User gives NL feedback ←──┐
                                               ↓              │
                                    LLM interprets & refines  │
                                               ↓              │
                                    Show DIFF of changes      │
                                               ↓              │
                                    User approves? ──NO───────┘
                                               ↓
                                            YES
                                               ↓
                                         Generate dbt
```

## New Functions

### 1. `llm_generate_detailed_plan()`
**Purpose:** Generate initial concrete plan with exact specifications

**Input:**
- Database schema
- Business context
- Heuristic classifications

**Output:** Detailed JSON plan with:
```json
{
  "bronze": ["customers", "orders", "products"],
  "silver": {
    "dimensions": [
      {
        "name": "dim_customers",
        "source_table": "customers",
        "scd_type": 2,
        "grain": "one row per customer per valid period",
        "primary_key": "customer_id",
        "columns": ["customer_id", "name", "email", "segment", "status"]
      }
    ],
    "facts": [
      {
        "name": "fct_orders",
        "source_table": "orders",
        "grain": "one row per order",
        "date_column": "order_date",
        "foreign_keys": [
          {"column": "customer_id", "references": "dim_customers"},
          {"column": "store_id", "references": "dim_stores"}
        ],
        "measures": ["total_amount", "discount_amount", "tax_amount"]
      }
    ]
  },
  "gold": [
    {
      "name": "gold_daily_revenue",
      "source_fact": "fct_orders",
      "grain": "daily",
      "date_column": "order_date",
      "metrics": [
        {"name": "total_revenue", "aggregation": "SUM", "column": "total_amount"},
        {"name": "order_count", "aggregation": "COUNT", "column": "*"}
      ],
      "description": "Daily revenue and order volume metrics"
    }
  ]
}
```

### 2. `display_concrete_plan()`
**Purpose:** Show plan in human-readable format with exact details

**Output Example:**
```
================================================================================
CONCRETE DATA MODEL PLAN
================================================================================

📦 BRONZE LAYER (Raw passthrough)
--------------------------------------------------------------------------------
  • bronze_customers
  • bronze_orders
  • bronze_products
  • bronze_order_items
  
Total: 14 tables (materialized as views)

================================================================================
🔷 SILVER LAYER - DIMENSIONS
================================================================================

dim_customers (SCD Type 2)
  Source: customers
  Grain: one row per customer per valid period
  Columns: customer_id, name, email, segment, status, created_at, updated_at

dim_products (SCD Type 2)
  Source: products
  Grain: one row per product per valid period
  Columns: product_id, name, category, price, cost, supplier_id

Total: 9 dimension tables

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
  Measures: total_amount, discount_amount, tax_amount, shipping_cost

fct_order_items
  Source: order_items
  Grain: one row per order line
  Date: order_date
  Foreign Keys:
    → order_id → fct_orders
    → product_id → dim_products
  Measures: quantity, unit_price, line_total, discount

Total: 5 fact tables

================================================================================
🥇 GOLD LAYER - PRE-AGGREGATED METRICS
================================================================================

DAILY AGGREGATES (3 tables):

  gold_daily_revenue
    Source: fct_orders
    Description: Daily revenue and order volume metrics
    Metrics:
      • total_revenue = SUM(total_amount)
      • order_count = COUNT(*)
      • avg_order_value = AVG(total_amount)

  gold_daily_product_sales
    Source: fct_order_items
    Description: Daily product sales performance
    Metrics:
      • units_sold = SUM(quantity)
      • revenue_by_product = SUM(line_total)

MONTHLY AGGREGATES (2 tables):

  gold_monthly_revenue
    Source: fct_orders
    Description: Monthly revenue trends and growth
    Metrics:
      • total_revenue = SUM(total_amount)
      • order_count = COUNT(*)
      • unique_customers = COUNT_DISTINCT(customer_id)

================================================================================
```

### 3. `llm_refine_plan()`
**Purpose:** Interpret natural language feedback and amend plan

**Input:**
- Current plan (JSON)
- User feedback (natural language string)
- Schema (for validation)
- Context (for business rules)

**Output:** Amended plan (complete JSON)

**Examples of feedback interpretation:**

| User Input | LLM Interpretation |
|------------|-------------------|
| "make orders weekly" | Change `gold_daily_orders` grain from "daily" to "weekly" |
| "split customers by type" | Create `dim_customers_b2b` and `dim_customers_b2c` from `dim_customers` |
| "add customer lifetime value" | Add `gold_customer_ltv` with CLV metric calculation |
| "remove product dimension" | Remove `dim_products`, update all facts that reference it |
| "orders should be daily grain" | Change `fct_orders` grain to daily aggregation |

### 4. `show_diff()`
**Purpose:** Display changes between iterations

**Output Example:**
```
================================================================================
CHANGES IN THIS ITERATION
================================================================================

  ✓ Added gold aggregate: gold_weekly_revenue
  ✗ Removed gold aggregate: gold_daily_revenue
  ⟳ Modified fact: fct_orders (added measure: tax_amount)
  ⟳ Modified dimension: dim_customers (changed SCD type: 1 → 2)

================================================================================
```

### 5. `interactive_refinement_loop()`
**Purpose:** Orchestrate the entire refinement process

**Flow:**
```python
def interactive_refinement_loop(schema, context, heuristics):
    # 1. Generate initial detailed plan
    plan = llm_generate_detailed_plan(schema, context, heuristics)
    
    iteration = 1
    while True:
        # 2. Show concrete plan
        display_concrete_plan(plan)
        
        # 3. Get user feedback
        feedback = input("Your feedback: ")
        
        # 4. Check for approval/rejection
        if feedback in ['approve', 'done']:
            return convert_to_modeling_plan(plan)
        if feedback in ['reject', 'cancel']:
            return None
        
        # 5. Refine plan
        old_plan = plan
        plan = llm_refine_plan(plan, feedback, schema, context)
        
        # 6. Show diff
        show_diff(old_plan, plan)
        
        iteration += 1
```

## Integration Steps

### Step 1: Add New Functions to `planner.py`
```python
# Copy all functions from planner_enhanced.py to your schemalytics/planner.py
```

### Step 2: Update `cli.py` Generate Command
```python
@click.command()
def generate(connection, output, name, context_file):
    # ... existing extraction code ...
    
    # Replace old user_review_loop() with:
    heuristic_classifications = classify_by_fk_graph(schema)
    modeling_plan = interactive_refinement_loop(
        schema, context, heuristic_classifications
    )
    
    # ... existing generation code ...
```

### Step 3: Update Imports
```python
# In cli.py, add:
from schemalytics.planner import (
    classify_by_fk_graph,
    interactive_refinement_loop
)
```

### Step 4: Remove Old Functions (optional cleanup)
- Remove old `user_review_loop()`
- Remove old `format_plan_for_review()` (replaced by `display_concrete_plan()`)
- Remove old `collect_user_edits()` (replaced by NL feedback)

## Usage Examples

### Example 1: Basic Approval
```bash
$ schemalytics generate -c postgresql://localhost/mydb

# User sees detailed plan...
Your feedback: approve

✓ Plan approved! Generating dbt project...
```

### Example 2: Change Time Grain
```bash
Your feedback: make revenue weekly instead of daily

Changes:
  ✗ Removed: gold_daily_revenue
  ✓ Added: gold_weekly_revenue
  
Your feedback: approve
```

### Example 3: Add New Metric
```bash
Your feedback: add a metric for customer lifetime value

Changes:
  ✓ Added: gold_customer_ltv
    Metrics:
      • lifetime_value = SUM(total_amount) grouped by customer_id
      • order_count = COUNT(*)
      
Your feedback: looks good
```

### Example 4: Split Dimension
```bash
Your feedback: split customers into B2B and B2C dimensions

Changes:
  ✗ Removed: dim_customers
  ✓ Added: dim_customers_b2b
  ✓ Added: dim_customers_b2c
  ⟳ Modified: fct_orders (updated FK references)
  
Your feedback: approve
```

### Example 5: Remove Unnecessary Table
```bash
Your feedback: we don't need the product dimension

Changes:
  ✗ Removed: dim_products
  ✗ Removed: gold_daily_product_sales
  ⟳ Modified: fct_order_items (removed FK to dim_products)
  
Your feedback: actually keep it

Changes:
  ✓ Added: dim_products (restored)
  ✓ Added: gold_daily_product_sales (restored)
  ⟳ Modified: fct_order_items (restored FK to dim_products)
  
Your feedback: approve
```

## Testing

### Test 1: Basic Flow
```python
# Test that detailed plan is generated
plan = llm_generate_detailed_plan(schema, context, classifications)
assert "bronze" in plan
assert "silver" in plan
assert "gold" in plan
```

### Test 2: Feedback Interpretation
```python
# Test that LLM interprets feedback correctly
plan = {"gold": [{"name": "gold_daily_revenue", "grain": "daily"}]}
feedback = "make revenue weekly"
new_plan = llm_refine_plan(plan, feedback, schema, context)
assert new_plan["gold"][0]["grain"] == "weekly"
```

### Test 3: Diff Detection
```python
# Test that changes are detected
old = {"gold": [{"name": "gold_daily_revenue"}]}
new = {"gold": [{"name": "gold_weekly_revenue"}]}
# Should show: removed daily, added weekly
```

## Benefits

1. **Concrete Specification** - Users see EXACTLY what will be created
2. **Natural Language** - No need to learn command syntax
3. **Iterative** - Refine until perfect, no limit
4. **Intelligent** - LLM validates and suggests alternatives
5. **Transparent** - Diff shows exactly what changed
6. **Flexible** - Handles any feedback phrasing

## Future Enhancements

1. **Preview SQL** - Show actual SQL that will be generated
2. **Validation Rules** - Stricter checks for impossible changes
3. **Templates** - Save/load common refinement patterns
4. **Undo** - Go back to previous iteration
5. **Branch** - Try multiple refinement paths
6. **Export Plan** - Save intermediate plans as YAML

## Files Changed

- ✅ `schemalytics/planner.py` - Added 5 new functions
- ✅ `schemalytics/cli.py` - Updated generate command
- 📝 `README.md` - Updated usage examples
- 📝 `CHANGELOG.md` - Document v0.2.0 changes

## Backward Compatibility

The old `user_review_loop()` can be kept for backward compatibility:
```python
# In cli.py
if use_legacy_mode:
    plan = user_review_loop(schema, context, llm_output)
else:
    plan = interactive_refinement_loop(schema, context, classifications)
```

Add a flag: `--legacy-mode` to use old behavior.