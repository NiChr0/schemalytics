-- Bronze: Raw passthrough from source
{{ config(materialized='view') }}

select *
from {{ source('raw', 'customer_demographics') }}
