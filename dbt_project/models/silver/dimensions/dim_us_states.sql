-- Dimension: dim_us_states (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['state_id']) }} as dim_us_states_sk,
    state_id,
    state_name,
    state_abbr,
    state_region,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_us_states') }}
