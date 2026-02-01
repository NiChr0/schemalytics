"""Generate dbt project from modeling plan."""
from pathlib import Path
from datetime import datetime
from jinja2 import Template
from schemalytics.models import Schema, ModelingPlan, BusinessContext
from schemalytics import templates


def render(template_str: str, **kwargs) -> str:
    """Render a Jinja2 template."""
    escaped = template_str.replace("{{ config", "{% raw %}{{ config{% endraw %}")
    escaped = escaped.replace("{{ source", "{% raw %}{{ source{% endraw %}")
    escaped = escaped.replace("{{ ref", "{% raw %}{{ ref{% endraw %}")
    escaped = escaped.replace("{{ dbt_utils", "{% raw %}{{ dbt_utils{% endraw %}")
    escaped = escaped.replace(") }}", ") }}{% raw %}{% endraw %}")
    
    return Template(escaped).render(**kwargs)


def format_columns(columns: list[str], indent: int = 4) -> str:
    """Format column list with one column per line."""
    spaces = " " * indent
    return ",\n".join(f"{spaces}{col}" for col in columns)


def generate_dbt_project(
    schema: Schema,
    plan: ModelingPlan,
    output_dir: str,
    project_name: str = "schemalytics_project",
    source_schema: str = "public",
    business_type: str = "generic",
    context: BusinessContext = None,
) -> Path:
    """Generate complete dbt project structure."""
    base = Path(output_dir)
    
    # Create directories
    dirs = [
        base,
        base / "models" / "bronze",
        base / "models" / "silver" / "dimensions",
        base / "models" / "silver" / "facts",
        base / "models" / "gold",
        base / "tests",
        base / "macros",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    
    # dbt_project.yml
    (base / "dbt_project.yml").write_text(
        render(templates.DBT_PROJECT_TEMPLATE, project_name=project_name)
    )
    
    # sources.yml
    (base / "models" / "sources.yml").write_text(
        render(templates.SOURCES_TEMPLATE, schema=source_schema, tables=plan.bronze)
    )
    
    # Bronze schema.yml
    bronze_columns = {}
    for table_name in plan.bronze:
        table = next((t for t in schema.tables if t.name == table_name), None)
        if table:
            bronze_columns[table_name] = table.columns
    
    if bronze_columns:
        # Update template to use stg_ prefix
        bronze_schema_yml = "version: 2\n\nmodels:\n"
        for table_name in plan.bronze:
            bronze_schema_yml += f"  - name: stg_{source_schema}_{table_name}\n"
            bronze_schema_yml += f"    description: \"Raw passthrough from {table_name} source table\"\n"
            if table_name in bronze_columns:
                bronze_schema_yml += "    columns:\n"
                for col in bronze_columns[table_name]:
                    bronze_schema_yml += f"      - name: {col.name}\n"
                    bronze_schema_yml += f"        description: \"{col.description or 'Column from source system'}\"\n"
                    bronze_schema_yml += f"        data_type: {col.data_type}\n"
        
        (base / "models" / "bronze" / "schema.yml").write_text(bronze_schema_yml)
    
    # Silver dimensions schema.yml
    if plan.dimensions:
        (base / "models" / "silver" / "dimensions" / "schema.yml").write_text(
            Template(templates.SILVER_DIMENSIONS_SCHEMA_TEMPLATE).render(dimensions=plan.dimensions)
        )
    
    # Silver facts schema.yml
    if plan.facts:
        (base / "models" / "silver" / "facts" / "schema.yml").write_text(
            Template(templates.SILVER_FACTS_SCHEMA_TEMPLATE).render(facts=plan.facts)
        )
    
    # Gold schema.yml
    if plan.gold:
        (base / "models" / "gold" / "schema.yml").write_text(
            Template(templates.GOLD_SCHEMA_TEMPLATE).render(gold_models=plan.gold)
        )
    
    # Bronze models
    for table in plan.bronze:
        sql = f"""-- Bronze: Raw passthrough from source
{{{{ config(materialized='view') }}}}

select *
from {{{{ source('raw', '{table}') }}}}
"""
        (base / "models" / "bronze" / f"stg_{source_schema}_{table}.sql").write_text(sql)
    
    # Dimension models
    for dim in plan.dimensions:
        if dim.scd_type == 1:
            cols = format_columns(dim.columns)
            sql = f"""-- Dimension: {dim.name} (SCD Type 1)
{{{{ config(materialized='table') }}}}

select
{cols}
from {{{{ ref('stg_{source_schema}_{dim.source_table}') }}}}
"""
        else:
            pk = dim.columns[0] if dim.columns else "id"
            cols = format_columns(dim.columns)
            sql = f"""-- Dimension: {dim.name} (SCD Type 2)
{{{{ config(materialized='table') }}}}

select
    {{{{ dbt_utils.generate_surrogate_key(['{pk}']) }}}} as {dim.name}_sk,
{cols},
    current_timestamp as valid_from,
    null::timestamp as valid_to,
    true as is_current
from {{{{ ref('stg_{source_schema}_{dim.source_table}') }}}}
"""
        (base / "models" / "silver" / "dimensions" / f"{dim.name}.sql").write_text(sql)
    
    # Fact models
    for fact in plan.facts:
        pk = fact.dimension_keys[0] if fact.dimension_keys else "id"
        all_cols = fact.dimension_keys + [fact.date_column] + fact.measures
        cols = format_columns(all_cols)
        sql = f"""-- Fact: {fact.name}
{{{{ config(materialized='table') }}}}

select
    {{{{ dbt_utils.generate_surrogate_key(['{pk}']) }}}} as {fact.name}_sk,
{cols}
from {{{{ ref('stg_{source_schema}_{fact.source_table}') }}}}
"""
        (base / "models" / "silver" / "facts" / f"{fact.name}.sql").write_text(sql)
    
    # Gold models
    for gold in plan.gold:
        grain_func = {
            "daily": "day",
            "monthly": "month",
            "yearly": "year"
        }.get(gold.grain, "day")
        
        # Build metrics SQL
        metrics_sql = []
        for metric in gold.metrics:
            if metric.aggregation == "COUNT_DISTINCT":
                metrics_sql.append(f"    count(distinct {metric.column}) as {metric.name}")
            elif metric.column == "*":
                metrics_sql.append(f"    count(*) as {metric.name}")
            else:
                metrics_sql.append(f"    {metric.aggregation.lower()}({metric.column}) as {metric.name}")
        
        # Build dimensions SQL
        dims_sql = []
        if gold.dimensions:
            dims_sql = [f"    {dim}," for dim in gold.dimensions]
        
        sql = f"""-- Gold: {gold.name}
-- {gold.description}
{{{{ config(materialized='table') }}}}

select
    date_trunc('{grain_func}', {gold.date_column}) as {gold.grain}_date,
{chr(10).join(dims_sql)}
{(','+chr(10)).join(metrics_sql)}
from {{{{ ref('{gold.source_fact}') }}}}
group by 1{', ' + ', '.join(str(i+2) for i in range(len(gold.dimensions))) if gold.dimensions else ''}
"""
        (base / "models" / "gold" / f"{gold.name}.sql").write_text(sql)
    
    # Semantic Layer YAML
    semantic_content = Template(templates.SEMANTIC_LAYER_TEMPLATE).render(
        project_name=project_name,
        timestamp=datetime.now().isoformat(),
        business_type=business_type,
        business_description=f"Generated dbt project for {business_type} analytics",
        gold_models=plan.gold,
        dimensions=plan.dimensions,
        facts=plan.facts,
        context_goals=context.goals if context else [],
    )
    (base / "semantic_layer.yml").write_text(semantic_content)
    
    # README
    readme = f"""# {project_name}

Generated by Schemalytics.

## Structure
- **bronze/**: Raw passthrough from source ({len(plan.bronze)} models)
- **silver/dimensions/**: Dimensional models ({len(plan.dimensions)} models)
- **silver/facts/**: Fact tables ({len(plan.facts)} models)
- **gold/**: Pre-aggregated metrics ({len(plan.gold)} models)

## Semantic Layer
See `semantic_layer.yml` for LLM-ready metadata including:
- Available metrics and their definitions
- Dimensional model structure
- Query patterns and guidelines

## Models

### Dimensions
{chr(10).join(f'- {d.name}: {d.grain}' for d in plan.dimensions)}

### Facts
{chr(10).join(f'- {f.name}: {f.grain}' for f in plan.facts)}

### Gold Aggregates
{chr(10).join(f'- {g.name} ({g.grain}): {g.description}' for g in plan.gold)}

## Usage with LLMs
The semantic layer provides structured metadata for LLM-powered analytics:
1. LLMs can read `semantic_layer.yml` to understand available metrics
2. Pre-aggregated Gold models provide fast query performance
3. Clear grain and dimension definitions help LLMs generate correct queries

Example LLM prompt:
```
Using the semantic layer in semantic_layer.yml, write a SQL query to analyze
daily revenue trends over the last 30 days.
```
"""
    (base / "README.md").write_text(readme)
    
    return base