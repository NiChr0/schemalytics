# Output Structure

After an approved refinement session, Schemalytics writes a complete dbt project to the output directory.

---

## Directory Layout

```
<output_dir>/
├── dbt_project.yml             # dbt project configuration
├── semantic_layer.yml          # LLM-ready metadata catalog
├── README.md                   # Auto-generated project documentation
└── models/
    ├── sources.yml             # Source system definitions
    ├── bronze/
    │   ├── schema.yml          # Tests and documentation
    │   └── stg_<schema>_<table>.sql   (one per source table)
    ├── silver/
    │   ├── dimensions/
    │   │   ├── schema.yml
    │   │   └── dim_<name>.sql        (one per dimension)
    │   └── facts/
    │       ├── schema.yml
    │       └── fct_<name>.sql        (one per fact)
    └── gold/
        ├── schema.yml
        └── agg_<grain>_<metric>.sql  (one per aggregate)
```

---

## Layers

### Bronze — Raw Staging

**Materialization:** Views
**Naming:** `stg_<schema>_<table>`

Bronze models are pass-through views directly over the source tables. No transformation, no filtering — just a clean interface to raw data.

```sql
-- stg_public_orders.sql
{{ config(materialized='view') }}

select * from {{ source('raw', 'orders') }}
```

**Purpose:** Decouple downstream models from source table names. If a source table is renamed, only the bronze model needs updating.

---

### Silver — Dimensional Models

#### Dimensions

**Materialization:** Tables
**Naming:** `dim_<name>`

**SCD Type 1** (current values only):
```sql
-- dim_categories.sql
{{ config(materialized='table') }}

select
    {{ dbt_utils.surrogate_key(['category_id']) }} as category_key,
    category_id,
    name,
    parent_category_id
from {{ ref('stg_public_categories') }}
```

**SCD Type 2** (full history):
```sql
-- dim_customers.sql
{{ config(materialized='table') }}

select
    {{ dbt_utils.surrogate_key(['customer_id', 'valid_from']) }} as customer_key,
    customer_id,
    company_name,
    email,
    current_timestamp as valid_from,
    cast('9999-12-31' as timestamp) as valid_to,
    true as is_current
from {{ ref('stg_public_customers') }}
```

#### Facts

**Materialization:** Tables
**Naming:** `fct_<name>`

```sql
-- fct_order_details.sql
{{ config(materialized='table') }}

select
    {{ dbt_utils.surrogate_key(['order_id', 'product_id']) }} as order_detail_key,
    od.order_id,
    od.product_id,
    od.quantity,
    od.unit_price,
    od.discount,
    od.quantity * od.unit_price as line_total   -- derived measure
from {{ ref('stg_public_order_details') }} od
```

**Derived measures** are computed columns declared during the refinement loop. They are rendered as `expression AS name` in the Silver fact SELECT and referenced by alias name in Gold models. Example refinement input:

```
"add line_total = quantity * unit_price as a derived measure on fct_order_details"
```

---

### Gold — Pre-Aggregated Metrics

**Materialization:** Tables
**Naming:** `agg_<grain>_<metric>`

```sql
-- agg_monthly_revenue.sql
{{ config(materialized='table') }}

select
    date_trunc('month', order_date) as month_date,
    sum(total_amount) as total_revenue,
    count(*) as order_count,
    avg(total_amount) as avg_order_value
from {{ ref('fct_orders') }}
group by 1
```

**Purpose:** Pre-compute expensive aggregations. Gold models are what BI tools and LLMs query directly.

---

## Schema YAML Files

Each layer has a `schema.yml` with column-level documentation and dbt tests:

```yaml
# models/silver/facts/schema.yml
version: 2

models:
  - name: fct_orders
    description: "One row per order. Grain: order_id."
    columns:
      - name: order_key
        description: "Surrogate key"
        tests:
          - unique
          - not_null
      - name: order_date
        tests:
          - not_null
      - name: total_amount
        tests:
          - not_null
```

---

## dbt_project.yml

```yaml
name: 'northwind'
version: '1.0.0'
config-version: 2

profile: 'northwind'

model-paths: ["models"]
test-paths: ["tests"]

models:
  northwind:
    bronze:
      +materialized: view
    silver:
      +materialized: table
    gold:
      +materialized: table
```

---

## semantic_layer.yml

The semantic layer is a comprehensive YAML metadata catalog designed for LLM consumption. See [Semantic Layer](Semantic-Layer) for the full specification.

---

## Running the Generated Project

```bash
cd <output_dir>

# Configure your connection in profiles.yml
# See: https://docs.getdbt.com/docs/core/connect-data-platform/profiles.yml

dbt deps          # Install dbt packages
dbt run           # Build all models
dbt test          # Run data quality tests
dbt docs generate # Build documentation site
dbt docs serve    # Open docs in browser
```

---

## Notes

- Schemalytics generates files only — it does not execute dbt
- The `tests/` and `macros/` directories are created empty, ready for your additions
- `dbt_utils` package is referenced in surrogate key macros — add it to `packages.yml` if not present
