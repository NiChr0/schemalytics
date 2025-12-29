-- Dimension: dim_shippers (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['shipper_id']) }} as dim_shippers_sk,
    shipper_id,
    company_name,
    phone,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_shippers') }}
