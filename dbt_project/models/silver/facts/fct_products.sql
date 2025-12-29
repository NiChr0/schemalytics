-- Fact: fct_products
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['category_id']) }} as fct_products_sk,
    category_id,
    supplier_id,
    created_at,
    unit_price,
    discontinued
from {{ ref('bronze_products') }}
