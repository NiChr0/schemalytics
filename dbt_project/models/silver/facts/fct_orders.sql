-- Fact: fct_orders
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['customer_id']) }} as fct_orders_sk,
    customer_id,
    employee_id,
    ship_via,
    order_date,
    freight
from {{ ref('bronze_orders') }}
