-- Gold: gold_daily_revenue
-- Daily revenue and order metrics
{{ config(materialized='table') }}

select
    date_trunc('day', order_date) as daily_date,

    sum(amount) as total_revenue,
    count(*) as order_count
from {{ ref('fct_orders') }}
group by 1
