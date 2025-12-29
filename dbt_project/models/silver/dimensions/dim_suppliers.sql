-- Dimension: dim_suppliers (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['supplier_id']) }} as dim_suppliers_sk,
    supplier_id,
    company_name,
    contact_name,
    contact_title,
    address,
    city,
    region,
    postal_code,
    country,
    phone,
    fax,
    homepage,
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_suppliers') }}
