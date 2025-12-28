"""dbt SQL templates using Jinja2."""

BRONZE_TEMPLATE = """-- Bronze: Raw passthrough from source
{{ config(materialized='view') }}

select *
from {{ source('raw', '{{ source_table }}') }}
"""

DIM_SCD1_TEMPLATE = """-- Dimension: {{ name }} (SCD Type 1)
{{ config(materialized='table') }}

select
    {% for col in columns %}
    {{ col }}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('bronze_{{ source_table }}') }}
"""

DIM_SCD2_TEMPLATE = """-- Dimension: {{ name }} (SCD Type 2)
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['{{ primary_key }}']) }} as {{ name }}_sk,
    {% for col in columns %}
    {{ col }},
    {% endfor %}
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{ ref('bronze_{{ source_table }}') }}
"""

FACT_TEMPLATE = """-- Fact: {{ name }}
{{ config(materialized='table') }}

select
    {{ dbt_utils.generate_surrogate_key(['{{ primary_key }}']) }} as {{ name }}_sk,
    {% for dk in dimension_keys %}
    {{ dk }},
    {% endfor %}
    {{ date_column }},
    {% for measure in measures %}
    {{ measure }}{% if not loop.last %},{% endif %}
    {% endfor %}
from {{ ref('bronze_{{ source_table }}') }}
"""

DBT_PROJECT_TEMPLATE = """name: '{{ project_name }}'
version: '1.0.0'
config-version: 2

profile: '{{ project_name }}'

model-paths: ["models"]
test-paths: ["tests"]
macro-paths: ["macros"]

target-path: "target"
clean-targets:
  - "target"
  - "dbt_packages"

models:
  {{ project_name }}:
    bronze:
      +materialized: view
    silver:
      +materialized: table
    gold:
      +materialized: table
"""

SOURCES_TEMPLATE = """version: 2

sources:
  - name: raw
    schema: {{ schema }}
    tables:
      {% for table in tables %}
      - name: {{ table }}
      {% endfor %}
"""
