-- Gold: gold_daily_conversion_rate
-- Daily conversion rate for employees
{{ config(materialized='table') }}

select
    date_trunc('day', order_date) as daily_date,
    employee_id,
    count(*) as total_conversions,
    count(order_id) as total_attempts
from {{ ref('fct_orders') }}
group by 1, 2
