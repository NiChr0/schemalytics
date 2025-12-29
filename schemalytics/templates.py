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

GOLD_AGGREGATE_TEMPLATE = """-- Gold: {{ name }}
{{ config(materialized='table') }}

select
    date_trunc('{{ grain_func }}', {{ date_column }}) as {{ grain }}_date,
    {% for dim in dimensions %}
    {{ dim }},
    {% endfor %}
    {% for metric in metrics %}
    {% if metric.aggregation == 'COUNT_DISTINCT' %}
    count(distinct {{ metric.column }}) as {{ metric.name }}{% if not loop.last %},{% endif %}
    {% elif metric.column == '*' %}
    count(*) as {{ metric.name }}{% if not loop.last %},{% endif %}
    {% else %}
    {{ metric.aggregation|lower }}({{ metric.column }}) as {{ metric.name }}{% if not loop.last %},{% endif %}
    {% endif %}
    {% endfor %}
from {{ ref(source_fact) }}
group by 1{% for i in range(dimensions|length) %}, {{ i + 2 }}{% endfor %}
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

SEMANTIC_LAYER_TEMPLATE = """# Semantic Layer - LLM Context
# This file provides structured metadata for LLM-powered analytics

version: 1.0
project: {{ project_name }}
generated_at: {{ timestamp }}

# Business Context
business_context:
  type: {{ business_type }}
  description: {{ business_description }}

# Data Model Layers
layers:
  bronze:
    description: Raw data passthrough from source systems
    materialization: view
    
  silver:
    description: Cleaned dimensional models (facts and dimensions)
    materialization: table
    
  gold:
    description: Pre-aggregated metrics for analytics
    materialization: table

# Available Metrics
metrics:
{% for gold in gold_models %}
  - name: {{ gold.name }}
    description: {{ gold.description }}
    grain: {{ gold.grain }}
    source: {{ gold.source_fact }}
    aggregations:
{% for metric in gold.metrics %}
      - name: {{ metric.name }}
        type: {{ metric.aggregation }}
        column: {{ metric.column }}
        description: {{ metric.description }}
{% endfor %}
    dimensions:
{% if gold.dimensions %}
{% for dim in gold.dimensions %}
      - {{ dim }}
{% endfor %}
{% else %}
      - time ({{ gold.grain }})
{% endif %}
    
{% endfor %}

# Dimensional Model
dimensions:
{% for dim in dimensions %}
  - name: {{ dim.name }}
    source_table: {{ dim.source_table }}
    type: SCD{{ dim.scd_type }}
    grain: {{ dim.grain }}
    description: Dimension table for {{ dim.source_table }}
    
{% endfor %}

facts:
{% for fact in facts %}
  - name: {{ fact.name }}
    source_table: {{ fact.source_table }}
    grain: {{ fact.grain }}
    date_column: {{ fact.date_column }}
    measures:
{% for measure in fact.measures %}
      - {{ measure }}
{% endfor %}
    dimensions:
{% for dk in fact.dimension_keys %}
      - {{ dk }}
{% endfor %}
    
{% endfor %}

# LLM Query Guidelines
query_guidelines:
  - Use Gold layer models for pre-aggregated metrics
  - Join Silver facts/dimensions for detailed analysis
  - Bronze layer is for raw data exploration only
  - All dates are in the {{ gold.date_column }} format
  - Metrics are pre-calculated in Gold models

# Common Query Patterns
query_patterns:
{% for gold in gold_models %}
  - pattern: "{{ gold.grain }} {{ gold.description }}"
    sql: "SELECT * FROM {{ gold.name }} WHERE {{ gold.date_column }} BETWEEN ? AND ?"
{% endfor %}
"""