-- Dimension: dim_categories (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['category_id']) }} as dim_categories_sk,
    category_id,
    category_name,
    description,
    picture,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_categories') }}
