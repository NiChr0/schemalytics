# Configuration

## context.yaml

Instead of answering interactive prompts every time, you can pre-configure your business context in a YAML file and pass it with the `-x` flag:

```bash
schemalytics generate \
  -c postgresql://localhost/mydb \
  -o ./dbt_project \
  -x context.yaml
```

---

## File Format

```yaml
# context.yaml

# Industry from the taxonomy (see Industry Templates wiki page)
industry: "E-commerce & Retail"

# Sub-type within the industry
business_type: "B2C"

# Key business entities to focus the model on
entities:
  - customers
  - orders
  - products
  - categories

# Analytical goals that drive gold layer metric selection
goals:
  - revenue tracking
  - customer cohort analysis
  - product performance
  - cart abandonment analysis

# Temporal tracking strategy
# "historical_tracking" → SCD Type 2 for dimensions (keeps full history)
# "current_only"        → SCD Type 1 for dimensions (overwrites)
temporal: historical_tracking

# Primary time grain for gold layer aggregates
# Options: transaction_level, daily, weekly, monthly
grain: transaction_level
```

---

## Field Reference

### `industry` (string, required)

The industry category. Must match one of the 14+ supported industries:

- `E-commerce & Retail`
- `SaaS & Software`
- `Finance & Fintech`
- `Healthcare`
- `Media & Entertainment`
- `Marketing & Advertising`
- `Education`
- `Logistics & Transportation`
- `Hospitality & Travel`
- `Real Estate`
- `Manufacturing`
- `Government & Public Sector`

See [Industry Templates](Industry-Templates) for sub-types and presets.

---

### `business_type` (string, optional)

The sub-type within the industry. Examples: `B2C`, `B2B`, `marketplace`, `SaaS`, `banking`.

If omitted, Schemalytics uses the first sub-type for the selected industry.

---

### `entities` (list of strings, required)

The core business entities the data model should focus on. These map directly to source tables and dimension/fact naming.

Examples:
```yaml
# E-commerce
entities: [customers, orders, products, inventory]

# SaaS
entities: [accounts, users, subscriptions, events]

# Finance
entities: [accounts, transactions, loans, customers]
```

---

### `goals` (list of strings, required)

Analytical questions or reporting areas the gold layer should serve. The LLM uses these to decide which metrics and aggregations to include.

Examples:
```yaml
# Revenue-focused
goals:
  - monthly revenue reporting
  - revenue by product category
  - customer lifetime value

# Retention-focused
goals:
  - customer churn analysis
  - cohort retention
  - reactivation tracking
```

---

### `temporal` (string, optional)

Controls how dimension history is tracked:

| Value | Behavior | Use when |
|-------|----------|----------|
| `historical_tracking` | SCD Type 2 — adds new row on change | You need to know "what was the customer's address at order time?" |
| `current_only` | SCD Type 1 — overwrites previous values | You only care about current state, history not needed |

Default: `historical_tracking`

---

### `grain` (string, optional)

Sets the default time grain for gold layer aggregates:

| Value | Gold layer output |
|-------|-------------------|
| `transaction_level` | No pre-aggregation; gold tables are fact-level |
| `daily` | `agg_daily_*` tables |
| `weekly` | `agg_weekly_*` tables |
| `monthly` | `agg_monthly_*` tables |

Default: `transaction_level`

You can always change the grain per-table during the interactive refinement loop.

---

## Example Files

### Northwind (E-commerce test database)

```yaml
industry: "E-commerce & Retail"
business_type: "B2C"
entities:
  - customers
  - orders
  - products
  - categories
  - suppliers
goals:
  - revenue tracking
  - order analysis
  - product performance
temporal: historical_tracking
grain: transaction_level
```

### SaaS product

```yaml
industry: "SaaS & Software"
business_type: "B2B"
entities:
  - accounts
  - users
  - subscriptions
  - features
  - events
goals:
  - MRR and ARR reporting
  - churn analysis
  - feature adoption
  - expansion revenue
temporal: current_only
grain: monthly
```

### Financial services

```yaml
industry: "Finance & Fintech"
business_type: "payments"
entities:
  - merchants
  - transactions
  - disputes
  - settlements
goals:
  - processing volume
  - authorization rates
  - dispute analysis
  - settlement reconciliation
temporal: historical_tracking
grain: daily
```

---

## Notes

- The context file is not required — if omitted, Schemalytics prompts interactively
- Values in the file serve as defaults; you can still refine the plan interactively after generation
- `context.yaml` is listed in `.gitignore` by default to avoid committing sensitive connection details alongside it
