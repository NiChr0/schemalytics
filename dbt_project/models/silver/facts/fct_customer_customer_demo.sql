-- Fact: fct_customer_customer_demo
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['customer_type_id']) }} as fct_customer_customer_demo_sk,
    customer_type_id,
    customer_id,
    created_at
from {{ ref('bronze_customer_customer_demo') }}
