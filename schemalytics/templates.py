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

BRONZE_SCHEMA_TEMPLATE = """version: 2

models:
{% for table in tables %}
  - name: bronze_{{ table }}
    description: "Raw passthrough from {{ table }} source table"
    columns:
{% for col in columns[table] %}
      - name: {{ col.name }}
        description: "{{ col.description or 'Column from source system' }}"
        data_type: {{ col.data_type }}
{% endfor %}
{% endfor %}
"""

SILVER_DIMENSIONS_SCHEMA_TEMPLATE = """version: 2

models:
{% for dim in dimensions %}
  - name: {{ dim.name }}
    description: "{{ dim.grain }}"
    meta:
      layer: silver
      type: dimension
      scd_type: {{ dim.scd_type }}
    columns:
{% if dim.scd_type == 2 %}
      - name: {{ dim.name }}_sk
        description: "Surrogate key for this dimension (system-generated)"
        tests:
          - unique
          - not_null
{% endif %}
{% for col in dim.columns[:10] %}
      - name: {{ col }}
        description: "{{ col.replace('_', ' ').title() }}"
{% endfor %}
{% if dim.scd_type == 2 %}
      - name: valid_from
        description: "Start date/time when this record version became active"
      - name: valid_to
        description: "End date/time when this record version became inactive (NULL if current)"
      - name: is_current
        description: "Flag indicating if this is the current active record"
{% endif %}
{% endfor %}
"""

SILVER_FACTS_SCHEMA_TEMPLATE = """version: 2

models:
{% for fact in facts %}
  - name: {{ fact.name }}
    description: "{{ fact.grain }}"
    meta:
      layer: silver
      type: fact
      grain: transaction
    columns:
      - name: {{ fact.name }}_sk
        description: "Surrogate key for this fact (system-generated)"
        tests:
          - unique
          - not_null
      
{% for dk in fact.dimension_keys %}
      - name: {{ dk }}
        description: "Foreign key to {{ dk.replace('_id', '') }} dimension"
        tests:
          - not_null
{% endfor %}
      
      - name: {{ fact.date_column }}
        description: "Primary date/time for this transaction"
        tests:
          - not_null
      
{% for measure in fact.measures %}
      - name: {{ measure }}
        description: "{{ measure.replace('_', ' ').title() }} - numeric measure"
{% endfor %}
{% endfor %}
"""

GOLD_SCHEMA_TEMPLATE = """version: 2

models:
{% for gold in gold_models %}
  - name: {{ gold.name }}
    description: "{{ gold.description }}"
    meta:
      layer: gold
      grain: {{ gold.grain }}
      refresh: daily
    columns:
      - name: {{ gold.grain }}_date
        description: "Date at {{ gold.grain }} grain"
        tests:
          - unique
          - not_null
      
{% for metric in gold.metrics %}
      - name: {{ metric.name }}
        description: "{{ metric.description }}"
        meta:
          aggregation: {{ metric.aggregation }}
          source_column: {{ metric.column }}
{% endfor %}
{% endfor %}
"""

# Include the enhanced semantic layer template content here
SEMANTIC_LAYER_TEMPLATE = """# Semantic Layer - LLM Analytics Guide
# This file provides comprehensive metadata for LLM-powered analytics

version: 2.0
project: {{ project_name }}
generated_at: {{ timestamp }}
database_type: PostgreSQL

# =============================================================================
# BUSINESS CONTEXT
# =============================================================================
business_context:
  industry: {{ business_type }}
  description: {{ business_description }}
  primary_use_cases:
{% for goal in context_goals %}
    - {{ goal }}
{% endfor %}

# =============================================================================
# DATA MODEL OVERVIEW
# =============================================================================
architecture:
  pattern: Medallion (Bronze → Silver → Gold)
  approach: Kimball dimensional modeling
  
layers:
  bronze:
    description: Raw data passthrough from source systems
    materialization: view
    purpose: Exact replica of source data for auditing and reprocessing
    query_usage: Rarely queried directly; use for data exploration only
    
  silver:
    description: Cleaned dimensional models (facts and dimensions)
    materialization: table
    purpose: Structured star schema for flexible analytical queries
    query_usage: Use for detailed analysis requiring granular data
    
  gold:
    description: Pre-aggregated metrics optimized for performance
    materialization: table
    purpose: Fast dashboards and common reporting use cases
    query_usage: Primary layer for analytics - always check Gold first

# =============================================================================
# METRICS CATALOG
# =============================================================================
metrics:
{% for gold in gold_models %}
  - name: {{ gold.name }}
    display_name: "{{ gold.description }}"
    layer: gold
    grain: {{ gold.grain }}
    source_fact: {{ gold.source_fact }}
    refresh_frequency: "Depends on dbt schedule (typically daily)"
    
    measures:
{% for metric in gold.metrics %}
      - name: {{ metric.name }}
        aggregation: {{ metric.aggregation }}
        source_column: {{ metric.column }}
        data_type: "{{ 'INTEGER' if metric.aggregation == 'COUNT' else 'NUMERIC' }}"
        description: {{ metric.description }}
        sql_formula: "{{ metric.aggregation }}({{ metric.column }})"
        null_handling: "NULLs are excluded from aggregations"
        use_cases:
{% if 'revenue' in metric.name.lower() %}
          - "Track total revenue by {{ gold.grain }}"
          - "Calculate revenue growth rates"
          - "Compare revenue across time periods"
{% elif 'count' in metric.name.lower() %}
          - "Monitor {{ gold.grain }} activity volume"
          - "Track growth in transaction count"
          - "Calculate conversion rates"
{% elif 'average' in metric.name.lower() or 'avg' in metric.name.lower() %}
          - "Analyze average values by {{ gold.grain }}"
          - "Track changes in average metrics over time"
          - "Benchmark against targets"
{% else %}
          - "Analyze {{ metric.name }} trends"
          - "Compare across time periods"
{% endif %}
        example_queries:
          - description: "Get {{ metric.name }} for last 30 days"
            sql: "SELECT {{ gold.grain }}_date, {{ metric.name }} FROM {{ gold.name }} WHERE {{ gold.date_column }} >= CURRENT_DATE - 30 ORDER BY {{ gold.grain }}_date"
          - description: "Compare {{ metric.name }} month-over-month"
            sql: "SELECT {{ gold.grain }}_date, {{ metric.name }}, LAG({{ metric.name }}) OVER (ORDER BY {{ gold.grain }}_date) as previous_period FROM {{ gold.name }}"
{% endfor %}
    
    time_column: {{ gold.date_column }}
    dimensions:
{% if gold.dimensions %}
{% for dim in gold.dimensions %}
      - {{ dim }}
{% endfor %}
{% else %}
      - "time ({{ gold.grain }})"
{% endif %}
    
    common_filters:
      - "WHERE {{ gold.grain }}_date >= CURRENT_DATE - INTERVAL '30 days'"
      - "WHERE {{ gold.grain }}_date BETWEEN '[start_date]' AND '[end_date]'"
      - "WHERE EXTRACT(YEAR FROM {{ gold.grain }}_date) = EXTRACT(YEAR FROM CURRENT_DATE)"
    
{% endfor %}

# =============================================================================
# DIMENSIONAL MODEL
# =============================================================================

## Dimensions (Descriptive Attributes)
dimensions:
{% for dim in dimensions %}
  - name: {{ dim.name }}
    display_name: "{{ dim.source_table | title }}"
    source_table: {{ dim.source_table }}
    type: SCD{{ dim.scd_type }}
    grain: {{ dim.grain }}
    description: {{ 'Historical tracking enabled - captures changes over time' if dim.scd_type == 2 else 'Current state only - overwrites on change' }}
    role: "Provides context and attributes for filtering and grouping"
    
    key_column: {{ dim.source_table }}_id
    
{% if dim.scd_type == 2 %}
    scd_columns:
      - valid_from: "Start date of this record version"
      - valid_to: "End date of this record version (NULL if current)"
      - is_current: "Boolean flag indicating current record"
    
    usage_notes:
      - "Always filter on is_current = TRUE for point-in-time queries"
      - "Join on surrogate key ({{ dim.name }}_sk) not natural key"
      - "For historical analysis, use valid_from/valid_to range"
{% endif %}
    
    common_attributes:
{% for col in dim.columns[:5] %}
      - {{ col }}
{% endfor %}
    
    typical_use_cases:
      - "Filter data by {{ dim.source_table }} attributes"
      - "Group metrics by {{ dim.source_table }} categories"
      - "Join to facts for detailed analysis"
    
{% endfor %}

## Facts (Measurable Events)
facts:
{% for fact in facts %}
  - name: {{ fact.name }}
    display_name: "{{ fact.source_table | title }}"
    source_table: {{ fact.source_table }}
    grain: {{ fact.grain }}
    description: "Transactional data capturing measurable events"
    
    date_column: {{ fact.date_column }}
    date_description: "Primary date for time-based analysis"
    
    measures:
{% for measure in fact.measures %}
      - name: {{ measure }}
        type: "Numeric - can be aggregated"
        typical_aggregations: [SUM, AVG, MIN, MAX, COUNT]
{% endfor %}
    
    dimension_keys:
{% for dk in fact.dimension_keys %}
      - {{ dk }}
{% endfor %}
    
    relationships:
{% for dk in fact.dimension_keys %}
      - foreign_key: {{ dk }}
        references: "dim_{{ dk.replace('_id', '') if dk.endswith('_id') else dk }}"
        cardinality: "many-to-one"
        description: "Each {{ fact.source_table }} record links to one {{ dk.replace('_id', '') }}"
{% endfor %}
    
    typical_use_cases:
      - "Detailed transaction-level analysis"
      - "Calculate custom metrics not available in Gold"
      - "Drill down from Gold aggregates"
    
    join_pattern: |
      SELECT 
        f.*,
{% for dk in fact.dimension_keys[:3] %}
        d_{{ loop.index }}.attribute_name
{% endfor %}
      FROM {{ fact.name }} f
{% for dk in fact.dimension_keys[:3] %}
      LEFT JOIN dim_{{ dk.replace('_id', '') if dk.endswith('_id') else dk }} d_{{ loop.index }} 
        ON f.{{ dk }} = d_{{ loop.index }}.{{ dk }}
{% endfor %}
      WHERE f.{{ fact.date_column }} >= CURRENT_DATE - 30
    
{% endfor %}

# =============================================================================
# RELATIONSHIPS & JOIN PATHS
# =============================================================================
relationships:
{% for fact in facts %}
{% for dk in fact.dimension_keys %}
  - from_table: {{ fact.name }}
    to_table: dim_{{ dk.replace('_id', '') if dk.endswith('_id') else dk }}
    relationship_type: many-to-one
    join_condition: "{{ fact.name }}.{{ dk }} = dim_{{ dk.replace('_id', '') if dk.endswith('_id') else dk }}.{{ dk }}"
    description: "Multiple {{ fact.source_table }} records can reference the same {{ dk.replace('_id', '') }}"
{% endfor %}
{% endfor %}

join_paths:
  - path_name: "fact_to_all_dimensions"
    description: "Standard star schema join pattern"
    example: |
      SELECT 
        f.*,
        d1.*,
        d2.*
      FROM {{ facts[0].name if facts else 'fact_table' }} f
      LEFT JOIN dim_table1 d1 ON f.key1 = d1.key1
      LEFT JOIN dim_table2 d2 ON f.key2 = d2.key2

# =============================================================================
# BUSINESS GLOSSARY
# =============================================================================
glossary:
{% for fact in facts %}
  {{ fact.date_column }}: "Primary timestamp for {{ fact.source_table }} - use for time-based filtering and grouping"
{% endfor %}
{% for gold in gold_models %}
  {{ gold.grain }}_grain: "Data aggregated at {{ gold.grain }} level - one row per {{ gold.grain }}"
{% endfor %}
  
common_terms:
  grain: "The level of detail - daily grain means one row per day"
  fact: "A measurable business event (orders, transactions, clicks)"
  dimension: "Descriptive attributes (customer name, product category)"
  measure: "Numeric value that can be aggregated (quantity, amount)"
  surrogate_key: "System-generated unique identifier (ends in _sk)"
  natural_key: "Business identifier (ends in _id)"

# =============================================================================
# QUERY GUIDELINES FOR LLMs
# =============================================================================
llm_query_guidelines:
  
  query_strategy:
    - "ALWAYS start with Gold layer if the metric exists"
    - "Use Silver (facts + dimensions) only when Gold doesn't have the metric"
    - "Avoid Bronze layer unless exploring raw source data"
    - "Gold is 10-100x faster than Silver for common queries"
  
  performance_tips:
    - "Filter on date columns first (indexed)"
    - "Use Gold models for dashboards and reporting"
    - "Join facts to dimensions, never dimension to dimension"
    - "Limit result sets with TOP/LIMIT when exploring"
  
  common_mistakes:
    - mistake: "Querying Bronze for analytics"
      solution: "Use Silver or Gold instead"
    - mistake: "Joining dimensions to each other"
      solution: "Always join through a fact table"
    - mistake: "Not filtering by date on large fact tables"
      solution: "Always include date filter on time-series data"
    - mistake: "Using SELECT * on fact tables"
      solution: "Specify only needed columns"
  
  date_handling:
    - "All date columns are in YYYY-MM-DD format"
    - "Use CURRENT_DATE for today"
    - "Use date_trunc('month', date_column) for monthly aggregations"
    - "Use INTERVAL '30 days' for relative date math"
  
  null_handling:
    - "LEFT JOIN preserves all fact records even if dimension is missing"
    - "Aggregations (SUM, AVG, COUNT) ignore NULL values"
    - "Use COALESCE(column, 0) to convert NULL to zero"

# =============================================================================
# QUERY LIBRARY (Common Analytical Questions)
# =============================================================================
query_library:
{% for gold in gold_models %}
  
  - category: "{{ gold.grain | title }} Analysis"
    queries:
      - question: "What is the {{ gold.metrics[0].name if gold.metrics else 'total' }} for the last 30 days?"
        sql: |
          SELECT 
            {{ gold.grain }}_date,
            {{ gold.metrics[0].name if gold.metrics else 'metric' }}
          FROM {{ gold.name }}
          WHERE {{ gold.grain }}_date >= CURRENT_DATE - 30
          ORDER BY {{ gold.grain }}_date DESC
        
      - question: "How does {{ gold.grain }} performance compare to previous period?"
        sql: |
          SELECT 
            {{ gold.grain }}_date,
            {{ gold.metrics[0].name if gold.metrics else 'metric' }},
            LAG({{ gold.metrics[0].name if gold.metrics else 'metric' }}) OVER (
              ORDER BY {{ gold.grain }}_date
            ) as previous_{{ gold.grain }},
            {{ gold.metrics[0].name if gold.metrics else 'metric' }} - LAG({{ gold.metrics[0].name if gold.metrics else 'metric' }}) OVER (
              ORDER BY {{ gold.grain }}_date
            ) as change
          FROM {{ gold.name }}
          WHERE {{ gold.grain }}_date >= CURRENT_DATE - 60
          ORDER BY {{ gold.grain }}_date DESC
{% endfor %}

  - category: "Cross-Fact Analysis"
    queries:
      - question: "Combine multiple facts for comprehensive analysis"
        sql: |
          -- Example: Join multiple fact tables through shared dimensions
          SELECT 
            d.dimension_attribute,
            f1.measure1,
            f2.measure2
          FROM {{ facts[0].name if facts else 'fact1' }} f1
          INNER JOIN {{ dimensions[0].name if dimensions else 'dim_table' }} d 
            ON f1.{{ facts[0].dimension_keys[0] if facts and facts[0].dimension_keys else 'key' }} = d.{{ facts[0].dimension_keys[0] if facts and facts[0].dimension_keys else 'key' }}
          LEFT JOIN {{ facts[1].name if facts|length > 1 else 'fact2' }} f2 
            ON d.{{ facts[0].dimension_keys[0] if facts and facts[0].dimension_keys else 'key' }} = f2.{{ facts[0].dimension_keys[0] if facts and facts[0].dimension_keys else 'key' }}

# =============================================================================
# DATA QUALITY & LIMITATIONS
# =============================================================================
data_quality:
  refresh_schedule: "Typically daily via dbt runs"
  
  known_limitations:
    - "Historical data only available from {{ timestamp.split('T')[0] }}"
    - "SCD Type 2 dimensions track changes, but not all dimensions are slowly changing"
    - "Gold layer aggregations are pre-computed and may not reflect real-time data"
  
  null_handling_rules:
    - "Foreign keys may be NULL if dimension record doesn't exist"
    - "Measures are NULL if not applicable to the record"
    - "Date columns should never be NULL in fact tables"
  
  best_practices:
    - "Always filter fact tables by date to improve performance"
    - "Use Gold layer for standard reporting metrics"
    - "Use Silver layer when custom calculations are needed"
    - "Validate results by checking row counts and aggregations"

# =============================================================================
# QUICK REFERENCE
# =============================================================================
quick_reference:
  
  table_naming:
    bronze: "bronze_[source_table]"
    silver_facts: "fct_[entity]"
    silver_dimensions: "dim_[entity]"
    gold: "gold_[grain]_[metric_type]"
  
  column_naming:
    surrogate_keys: "[table]_sk (system-generated unique ID)"
    natural_keys: "[entity]_id (business identifier)"
    date_columns: "[event]_date or [grain]_date"
    measures: "Descriptive names like total_amount, quantity, etc."
  
  typical_workflow:
    1: "Identify the business question"
    2: "Check if Gold layer has the metric → use Gold"
    3: "If not in Gold, query Silver facts + dimensions"
    4: "Filter by date range to limit data"
    5: "Join dimensions only as needed"
    6: "Validate results make business sense"

---
# End of Semantic Layer
# For questions or issues, refer to dbt project documentation
"""