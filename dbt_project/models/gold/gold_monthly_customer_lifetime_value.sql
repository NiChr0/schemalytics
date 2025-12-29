-- Gold: gold_monthly_customer_lifetime_value
-- Monthly customer lifetime value
{{ config(materialized='table') }}

select
    date_trunc('month', created_at) as monthly_date,
    customer_id,
    sum(unit_price * quantity - discount) as lifetime_revenue,
    count(*) as order_count
from {{ ref('fct_order_details') }}
group by 1, 2
