-- Bronze: Raw passthrough from source
{{ config(materialized='view') }}

select *
from {{ source('raw', 'us_states') }}
