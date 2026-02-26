# Semantic Layer

After generation, Schemalytics creates a `semantic_layer.yml` file alongside the dbt models. This is a comprehensive metadata catalog designed to give LLMs everything they need to write accurate SQL queries against your data warehouse.

---

## Purpose

The semantic layer bridges the gap between raw SQL and natural language analytics. Instead of asking an LLM to guess what `fct_orders.c3` means, you give it:

- Human-readable descriptions of every table and column
- Explicit metric definitions (what aggregation, which column)
- Relationship maps between tables
- Example queries for common analytical patterns
- Business context (industry, goals, key entities)

Any LLM given this file can answer questions like "What was monthly revenue last quarter?" by referencing the gold layer metrics instead of trying to construct aggregations from scratch.

---

## Structure

```yaml
semantic_layer:
  project: northwind
  generated_at: "2026-01-15T10:30:00"
  version: "0.1.3"

  business_context:
    industry: "E-commerce & Retail"
    description: "..."
    key_entities: [customers, orders, products]
    analytical_goals: [revenue tracking, customer analysis]

  data_sources:
    - name: orders
      description: "Raw orders table from the transactional database"
      schema: public
      table: orders

  bronze_layer:
    - model: stg_public_orders
      description: "Raw passthrough view of the orders table"
      source: orders
      columns:
        - name: order_id
          description: "Primary key"
          type: integer
        - name: order_date
          description: "Date the order was placed"
          type: date

  silver_layer:
    dimensions:
      - model: dim_customers
        description: "Customer dimension with full history (SCD Type 2)"
        grain: "One row per customer per valid period"
        scd_type: 2
        primary_key: customer_key
        columns:
          - name: customer_key
            description: "Surrogate key"
          - name: customer_id
            description: "Natural key from source"
          - name: company_name
            description: "Customer company name"
          - name: valid_from
            description: "Record effective start date"
          - name: valid_to
            description: "Record effective end date (9999-12-31 = current)"
          - name: is_current
            description: "True if this is the current record"

    facts:
      - model: fct_orders
        description: "One row per order. Central fact table."
        grain: "order_id"
        date_column: order_date
        foreign_keys:
          - column: customer_key
            references: dim_customers.customer_key
        measures:
          - name: total_amount
            description: "Order total including tax and shipping"
            type: decimal
          - name: discount
            description: "Discount applied to order"
            type: decimal

  gold_layer:
    - model: agg_monthly_revenue
      description: "Monthly revenue and order volume metrics"
      grain: monthly
      source_fact: fct_orders
      metrics:
        - name: total_revenue
          description: "Sum of all order totals"
          calculation: "SUM(total_amount)"
          format: currency
        - name: order_count
          description: "Number of orders placed"
          calculation: "COUNT(*)"
          format: integer
        - name: avg_order_value
          description: "Average order total"
          calculation: "AVG(total_amount)"
          format: currency

  relationships:
    - from: fct_orders.customer_key
      to: dim_customers.customer_key
      type: many_to_one

  metrics_catalog:
    - name: total_revenue
      description: "Total revenue from all orders"
      model: agg_monthly_revenue
      column: total_revenue
      aggregation: sum
      filters: []
    - name: monthly_active_customers
      description: "Unique customers who placed at least one order"
      model: agg_monthly_revenue
      column: unique_customers
      aggregation: count_distinct

  query_patterns:
    - name: monthly_revenue_trend
      description: "Revenue trend over time"
      sql: |
        SELECT month_date, total_revenue, order_count
        FROM agg_monthly_revenue
        ORDER BY month_date
    - name: top_customers_by_revenue
      description: "Customers ranked by lifetime revenue"
      sql: |
        SELECT customer_key, SUM(total_amount) as lifetime_value
        FROM fct_orders
        GROUP BY customer_key
        ORDER BY lifetime_value DESC
        LIMIT 20
```

---

## Using the Semantic Layer with LLMs

### System prompt pattern

The simplest way to enable LLM-powered analytics is to include `semantic_layer.yml` in your LLM's system prompt or context:

```python
import yaml

with open("dbt_project/semantic_layer.yml") as f:
    semantic_layer = yaml.safe_load(f)

system_prompt = f"""
You are a data analyst assistant with access to the following data warehouse.
Use the semantic layer below to write accurate SQL queries.

{yaml.dump(semantic_layer)}

When answering analytics questions:
1. Prefer gold layer models (agg_*) for aggregated metrics
2. Use silver layer (dim_*, fct_*) for detailed analysis
3. Always use the model names exactly as defined
4. Reference relationships defined in the semantic layer
"""
```

### Example interaction

With the semantic layer loaded:

**User:** "What was total revenue last month?"

**LLM (with semantic layer):**
```sql
SELECT total_revenue
FROM agg_monthly_revenue
WHERE month_date = DATE_TRUNC('month', CURRENT_DATE - INTERVAL '1 month')
```

Without the semantic layer, the LLM would have to guess table names, column names, and aggregation logic.

---

## Integration Examples

### dbt Semantic Layer (MetricFlow)

The `semantic_layer.yml` is not the same as dbt's MetricFlow semantic layer, but the metrics catalog maps directly to `metrics:` blocks in dbt:

```yaml
# In your dbt project metrics.yml
metrics:
  - name: total_revenue
    label: Total Revenue
    model: ref('agg_monthly_revenue')
    description: "{{ doc('total_revenue') }}"
    type: simple
    type_params:
      measure:
        name: total_revenue
        agg: sum
```

### LangChain / LlamaIndex

Pass the semantic layer YAML as a document to your vector store or context window:

```python
from langchain.document_loaders import TextLoader

loader = TextLoader("dbt_project/semantic_layer.yml")
docs = loader.load()
# Add to your retriever or context
```
