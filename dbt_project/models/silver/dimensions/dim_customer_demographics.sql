-- Dimension: dim_customer_demographics (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['customer_type_id']) }} as dim_customer_demographics_sk,
    customer_type_id,
    customer_desc,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_customer_demographics') }}
