-- Gold: gold_yearly_product_performance
-- Yearly product performance metrics
{{ config(materialized='table') }}

select
    date_trunc('year', created_at) as yearly_date,
    product_id,
    sum(unit_price * quantity - discount) as total_revenue,
    count(*) as order_count
from {{ ref('fct_order_details') }}
group by 1, 2
