-- Dimension: dim_employees (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['employee_id']) }} as dim_employees_sk,
    employee_id,
    last_name,
    first_name,
    title,
    title_of_courtesy,
    birth_date,
    hire_date,
    address,
    city,
    region,
    postal_code,
    country,
    home_phone,
    extension,
    photo,
    notes,
    reports_to,
    photo_path,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_employees') }}
