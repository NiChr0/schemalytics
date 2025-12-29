-- Dimension: dim_territories (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['territory_id']) }} as dim_territories_sk,
    territory_id,
    territory_description,
    region_id,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_territories') }}
