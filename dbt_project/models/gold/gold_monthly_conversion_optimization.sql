-- Gold: gold_monthly_conversion_optimization
-- Monthly conversion optimization metrics
{{ config(materialized='table') }}

select
    date_trunc('month', order_date) as monthly_date,
    customer_id,
    avg((CASE WHEN order_status = 'Completed' THEN 1 ELSE 0 END)) as conversion_rate,
    avg(amount) as average_order_value
from {{ ref('fct_orders') }}
group by 1, 2
