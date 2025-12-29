-- Fact: fct_employee_territories
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['employee_id']) }} as fct_employee_territories_sk,
    employee_id,
    territory_id,
    created_at
from {{ ref('bronze_employee_territories') }}
