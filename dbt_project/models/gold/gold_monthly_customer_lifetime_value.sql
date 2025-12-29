-- Gold: gold_monthly_customer_lifetime_value
-- Monthly Customer Lifetime Value (CLV)
{{ config(materialized='table') }}

select
    date_trunc('month', created_at) as monthly_date,
    customer_id,
    sum(unit_price * quantity - discount) as total_spent,
    count(*) as order_count
from {{ ref('fct_order_details') }}
group by 1, 2
