-- Dimension: dim_region (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['region_id']) }} as dim_region_sk,
    region_id,
    region_description,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_region') }}
