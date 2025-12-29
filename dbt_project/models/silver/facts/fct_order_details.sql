-- Fact: fct_order_details
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['order_id']) }} as fct_order_details_sk,
    order_id,
    product_id,
    created_at,
    unit_price,
    discount
from {{ ref('bronze_order_details') }}
