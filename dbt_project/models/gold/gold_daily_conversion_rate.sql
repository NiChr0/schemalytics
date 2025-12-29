-- Gold: gold_daily_conversion_rate
-- Daily conversion rate by campaign
{{ config(materialized='table') }}

select
    date_trunc('day', order_date) as daily_date,
    campaign_id,
    count(*) as conversion_count,
    count(*) as total_order_count
from {{ ref('fct_orders') }}
group by 1, 2
