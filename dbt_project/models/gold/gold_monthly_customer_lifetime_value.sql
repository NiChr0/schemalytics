-- Gold: gold_monthly_customer_lifetime_value
-- Monthly customer lifetime value and transaction metrics
{{ config(materialized='table') }}

select
    date_trunc('month', transaction_date) as monthly_date,
    customer_id,
    sum(amount) as lifetime_value,
    count(*) as transaction_count
from {{ ref('fct_transactions') }}
group by 1, 2
