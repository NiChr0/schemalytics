-- Gold: gold_daily_inventory_tracking
-- Daily inventory tracking and sales metrics
{{ config(materialized='table') }}

select
    date_trunc('day', created_at) as daily_date,
    product_id,
    sum(quantity) as total_units_sold,
    sum(unit_price * quantity - discount) as total_revenue
from {{ ref('fct_order_details') }}
group by 1, 2
