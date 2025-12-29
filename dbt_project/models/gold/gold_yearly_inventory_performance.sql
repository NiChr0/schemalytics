-- Gold: gold_yearly_inventory_performance
-- Yearly inventory performance metrics
{{ config(materialized='table') }}

select
    date_trunc('year', transaction_date) as yearly_date,
    product_id,
    sum(quantity) as total_quantity_sold,
    sum(amount) as total_revenue_from_sales
from {{ ref('fct_inventory_transactions') }}
group by 1, 2
