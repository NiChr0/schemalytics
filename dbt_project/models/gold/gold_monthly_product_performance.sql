-- Gold: gold_monthly_product_performance
-- Monthly product performance metrics
{{ config(materialized='table') }}

select
    date_trunc('month', sale_date) as monthly_date,
    product_id,
    sum(amount) as total_revenue,
    avg(amount) as average_order_value
from {{ ref('fct_sales') }}
group by 1, 2
