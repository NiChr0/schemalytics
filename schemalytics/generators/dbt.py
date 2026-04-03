"""Generate dbt project from modeling plan."""
from pathlib import Path
from datetime import datetime
from jinja2 import Template
from schemalytics.models import Schema, ModelingPlan, BusinessContext, PipelineContext, SemanticLayer
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


_DATE_TYPES = {"date"}
_TIMESTAMP_TYPES = {
    "timestamp", "timestamptz", "datetime",
    "timestamp without time zone", "timestamp with time zone",
}
# Column names that indicate a dbt snapshot should use timestamp strategy.
_UPDATED_AT_COLS = {
    "updated_at", "modified_at", "last_modified_at", "last_updated_at",
    "modified_on", "updated_on", "last_modified", "date_modified",
}


def _staging_select(table) -> str:
    """Explicit SELECT column list for staging models with date/timestamp casts."""
    lines = []
    for col in table.columns:
        dt = col.data_type.lower()
        if dt in _DATE_TYPES:
            lines.append(f"    {col.name}::date as {col.name}")
        elif dt in _TIMESTAMP_TYPES:
            lines.append(f"    {col.name}::timestamp as {col.name}")
        else:
            lines.append(f"    {col.name}")
    return ",\n".join(lines)


def _updated_at_col(table) -> str | None:
    """Return the name of an updated_at-style column if one exists, else None."""
    col_names = {c.name.lower() for c in table.columns}
    for name in _UPDATED_AT_COLS:
        if name in col_names:
            return name
    return None


def _snapshot_sql(table_name: str, pk: str, updated_at: str | None, schema_name: str = "raw") -> str:
    """Generate a dbt snapshot file for SCD Type 2 tracking.

    Uses string concatenation for {%...%} and {{...}} blocks to avoid
    f-string / .format() brace-escaping conflicts.
    """
    if updated_at:
        strategy_lines = [
            "        strategy='timestamp',",
            f"        updated_at='{updated_at}',",
        ]
    else:
        strategy_lines = [
            "        strategy='check',",
            "        check_cols='all',",
        ]
    # Build the file line by line without any template escaping.
    OB, CB = "{{", "}}"  # dbt Jinja delimiters as plain strings
    lines = [
        "{%" + f" snapshot snap_{table_name} " + "%}",
        "",
        OB,
        "    config(",
        "        target_schema='snapshots',",
        f"        unique_key='{pk}',",
        *strategy_lines,
        "    )",
        CB,
        "",
        "select * from " + OB + f" source('{schema_name}', '{table_name}') " + CB,
        "",
        "{%" + " endsnapshot " + "%}",
        "",
    ]
    return "\n".join(lines)



def _write_semantic_layer(semantic_layer: SemanticLayer, base: Path) -> None:
    """Write dbt-native semantic_models.yml from Agent 6 output."""
    lines = ["version: 2", "", "semantic_models:"]
    for sm in semantic_layer.semantic_models:
        lines += [
            f"  - name: {sm.name}",
            f"    description: \"{sm.description}\"",
            f"    model: ref('{sm.model}')",
            "    entities:",
        ]
        for e in sm.entities:
            lines += [
                f"      - name: {e.name}",
                f"        type: {e.type}",
                f"        expr: {e.expr}",
            ]
        lines.append("    dimensions:")
        for d in sm.dimensions:
            lines += [
                f"      - name: {d.name}",
                f"        type: {d.type}",
                f"        expr: {d.expr}",
                f"        description: \"{d.description}\"",
            ]
            if d.type == "time" and d.time_granularity:
                lines += [
                    "        type_params:",
                    f"          time_granularity: {d.time_granularity}",
                ]
        lines.append("    measures:")
        for m in sm.measures:
            lines += [
                f"      - name: {m.name}",
                f"        agg: {m.agg}",
                f"        expr: {m.expr}",
                f"        description: \"{m.description}\"",
            ]
        lines.append("")

    if semantic_layer.metrics:
        lines += ["metrics:"]
        for metric in semantic_layer.metrics:
            lines += [
                f"  - name: {metric.name}",
                f"    label: \"{metric.label}\"",
                f"    description: \"{metric.description}\"",
                f"    type: {metric.type}",
                "    type_params:",
            ]
            for k, v in metric.type_params.items():
                lines.append(f"      {k}: {v}")
            lines.append("")

    (base / "semantic_models.yml").write_text("\n".join(lines))


def generate_dbt_project(
    schema: Schema,
    plan: ModelingPlan,
    output_dir: str,
    project_name: str = "schemalytics_project",
    source_schema: str = "public",
    business_type: str = "generic",
    context: BusinessContext | PipelineContext | None = None,
    semantic_layer: SemanticLayer | None = None,
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
        base / "snapshots",
        base / "tests",
        base / "macros",
    ]
    for d in dirs:
        d.mkdir(parents=True, exist_ok=True)
    
    # dbt_project.yml
    (base / "dbt_project.yml").write_text(
        render(templates.DBT_PROJECT_TEMPLATE, project_name=project_name)
    )

    # packages.yml — pinned version for reproducible builds
    (base / "packages.yml").write_text(
        "packages:\n  - package: dbt-labs/dbt_utils\n    version: \"1.3.0\"\n"
    )

    # macros/incremental_date_filter.sql — shared incremental filter used by all fact models.
    # Using a macro avoids copy-pasting the same {% if is_incremental() %} block across
    # every fact and makes the lookback window configurable in one place.
    (base / "macros" / "incremental_date_filter.sql").write_text(
        "{% macro incremental_date_filter(filter_col, max_col=none) %}\n"
        "    {% if is_incremental() %}\n"
        "    where {{ filter_col }} > (\n"
        "        select max({{ max_col or filter_col }})\n"
        "            - interval '{{ var(\"incremental_lookback_days\", 7) }} days'\n"
        "        from {{ this }}\n"
        "    )\n"
        "    {% endif %}\n"
        "{% endmacro %}\n"
    )

    # macros/generate_schema_name.sql — routes each layer to its own warehouse schema
    # so bronze/silver/gold land in separate schemas rather than the profile default.
    (base / "macros" / "generate_schema_name.sql").write_text(
        "{% macro generate_schema_name(custom_schema_name, node) -%}\n"
        "    {%- set default_schema = target.schema -%}\n"
        "    {%- if custom_schema_name is none -%}\n"
        "        {{ default_schema }}\n"
        "    {%- else -%}\n"
        "        {{ custom_schema_name | trim }}\n"
        "    {%- endif -%}\n"
        "{%- endmacro %}\n"
    )
    
    # Build early lookups used across schema.yml and SQL generation
    schema_table_map = {t.name: t for t in schema.tables}

    def _tbl_schema(table_name: str) -> str:
        """Return the schema name for a table, falling back to source_schema."""
        obj = schema_table_map.get(table_name)
        return obj.schema_name if obj else source_schema

    # Pre-compute effective date column for each fact (accounts for FK date joins in Fix C).
    fact_effective_dates: dict[str, str] = {}
    for _fact in plan.facts:
        if _fact.date_column:
            fact_effective_dates[_fact.name] = _fact.date_column
            continue
        _src = schema_table_map.get(_fact.source_table)
        if _src:
            for _fk in _src.foreign_keys:
                _parent = schema_table_map.get(_fk.references_table)
                if _parent:
                    _dc = next(
                        (c for c in _parent.columns if c.data_type.lower() in _DATE_TYPES | _TIMESTAMP_TYPES),
                        None,
                    )
                    if _dc:
                        fact_effective_dates[_fact.name] = f"{_fk.references_table}_{_dc.name}"
                        break

    # sources.yml — one source block per user schema found in plan.bronze
    _tables_by_schema: dict[str, list[str]] = {}
    for _t in plan.bronze:
        _tables_by_schema.setdefault(_tbl_schema(_t), []).append(_t)
    _sources_yml = "version: 2\n\nsources:\n"
    for _sn, _tnames in sorted(_tables_by_schema.items()):
        _sources_yml += f"  - name: {_sn}\n    schema: {_sn}\n    tables:\n"
        for _tn in _tnames:
            _sources_yml += f"      - name: {_tn}\n"
            _tbl_obj = schema_table_map.get(_tn)
            if _tbl_obj:
                _upd_col = _updated_at_col(_tbl_obj)
                if _upd_col:
                    _sources_yml += (
                        f"        loaded_at_field: {_upd_col}\n"
                        f"        freshness:\n"
                        f"          warn_after: {{count: 24, period: hour}}\n"
                        f"          error_after: {{count: 48, period: hour}}\n"
                    )
    (base / "models" / "sources.yml").write_text(_sources_yml)

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
            bronze_schema_yml += f"  - name: stg_{_tbl_schema(table_name)}_{table_name}\n"
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
        dim_names = {d.name for d in plan.dimensions}
        # Build nullability map per fact from the source table schema.
        # Used by the template to gate not_null tests — nullable-by-design columns
        # (e.g. period-end dates, optional FKs) must not get not_null tests.
        nullable_cols: dict[str, set[str]] = {}
        for _f in plan.facts:
            _tbl = schema_table_map.get(_f.source_table)
            nullable_cols[_f.name] = (
                {c.name for c in _tbl.columns if c.nullable} if _tbl else set()
            )
        (base / "models" / "silver" / "facts" / "schema.yml").write_text(
            Template(templates.SILVER_FACTS_SCHEMA_TEMPLATE).render(
                facts=plan.facts, dim_names=dim_names, nullable_cols=nullable_cols
            )
        )
    
    # Gold schema.yml
    if plan.gold:
        (base / "models" / "gold" / "schema.yml").write_text(
            Template(templates.GOLD_SCHEMA_TEMPLATE).render(
                gold_models=plan.gold,
                fact_effective_dates=fact_effective_dates,
            )
        )
    
    # Bronze models — explicit column select with type casts (not select *)
    for table in plan.bronze:
        source_table_obj = schema_table_map.get(table)
        tbl_schema = _tbl_schema(table)
        col_select = _staging_select(source_table_obj) if source_table_obj else "    *"
        sql = f"""-- Bronze: Staging from source (explicit columns + type casts)
select
{col_select}
from {{{{ source('{tbl_schema}', '{table}') }}}}
"""
        (base / "models" / "bronze" / f"stg_{tbl_schema}_{table}.sql").write_text(sql)
    
    # Dimension models
    for dim in plan.dimensions:
        source_table_obj = schema_table_map.get(dim.source_table)
        dim_src_schema = _tbl_schema(dim.source_table)
        if dim.scd_type == 1:
            cols = format_columns(dim.columns)
            if source_table_obj and source_table_obj.primary_key:
                scd1_pk = "', '".join(source_table_obj.primary_key)
            else:
                scd1_pk = dim.columns[0] if dim.columns else "id"
            sql = f"""-- Dimension: {dim.name} (SCD Type 1)
{{{{ config(materialized='table') }}}}

select
    {{{{ dbt_utils.generate_surrogate_key(['{scd1_pk}']) }}}} as {dim.name}_sk,
{cols}
from {{{{ ref('stg_{dim_src_schema}_{dim.source_table}') }}}}
"""
        else:
            # SCD Type 2: backed by a dbt snapshot.
            # The snapshot tracks row-level changes; this model is a view on top.
            # Prerequisite: run `dbt snapshot` before `dbt run`.
            cols = format_columns(dim.columns)

            # Determine primary key and snapshot strategy.
            if source_table_obj and source_table_obj.primary_key:
                snap_pk = source_table_obj.primary_key[0]
            else:
                snap_pk = dim.columns[0] if dim.columns else "id"
            updated_at = _updated_at_col(source_table_obj) if source_table_obj else None

            # Write the snapshot file.
            snap_path = base / "snapshots" / f"snap_{dim.source_table}.sql"
            snap_path.write_text(_snapshot_sql(dim.source_table, snap_pk, updated_at, dim_src_schema))

            # Dimension reads from the snapshot using dbt's built-in SCD columns.
            sql = f"""-- Dimension: {dim.name} (SCD Type 2)
-- History tracked by snapshot: snap_{dim.source_table}
-- Run `dbt snapshot` before `dbt run` to populate historical records.
{{{{ config(materialized='table') }}}}

select
    dbt_scd_id as {dim.name}_sk,
{cols},
    dbt_valid_from as valid_from,
    dbt_valid_to as valid_to,
    (dbt_valid_to is null) as is_current
from {{{{ ref('snap_{dim.source_table}') }}}}
"""
        (base / "models" / "silver" / "dimensions" / f"{dim.name}.sql").write_text(sql)
    
    # Fact models
    for fact in plan.facts:
        source_table_obj = schema_table_map.get(fact.source_table)

        # Build surrogate key columns from the natural PK.
        # For periodic snapshots (identified by the date column appearing in dimension_keys
        # but not in the natural PK), include the date column so uniqueness holds across
        # time slices — e.g. productinventory needs (productid, locationid, modifieddate).
        if source_table_obj and source_table_obj.primary_key:
            sk_cols = list(source_table_obj.primary_key)
            pk_cols = source_table_obj.primary_key
        else:
            sk_cols = [fact.dimension_keys[0]] if fact.dimension_keys else ["id"]
            pk_cols = []
        if (fact.date_column
                and fact.date_column in fact.dimension_keys
                and fact.date_column not in sk_cols):
            sk_cols = sk_cols + [fact.date_column]
        pk_str = "', '".join(sk_cols)
        extra_pk = [c for c in pk_cols if c not in fact.dimension_keys]

        # Fix C: auto-add LEFT JOIN to parent table when fact has no date column.
        # Track date_raw_expr (WHERE predicate) separately from the SELECT alias.
        join_clause = ""
        date_raw_expr = fact.date_column  # raw SQL expression for WHERE clause
        date_cols = [fact.date_column] if fact.date_column else []
        fact_src_schema = _tbl_schema(fact.source_table)
        if not fact.date_column and source_table_obj:
            for fk in source_table_obj.foreign_keys:
                parent = schema_table_map.get(fk.references_table)
                if parent:
                    dc = next(
                        (c for c in parent.columns if c.data_type.lower() in _DATE_TYPES | _TIMESTAMP_TYPES),
                        None,
                    )
                    if dc:
                        joined_alias = f"{fk.references_table}_{dc.name}"
                        date_raw_expr = f"{fk.references_table}.{dc.name}"
                        date_cols = [f"{date_raw_expr} as {joined_alias}"]
                        parent_schema = _tbl_schema(fk.references_table)
                        join_clause = (
                            f"left join {{{{ ref('stg_{parent_schema}_{fk.references_table}') }}}}"
                            f" {fk.references_table}\n"
                            f"    on fact_src.{fk.column} = "
                            f"{fk.references_table}.{fk.references_column}"
                        )
                        break

        # Derived measures: render as "expression AS name" so downstream Gold models
        # can reference them by their alias without re-deriving the expression.
        derived_cols = [f"{dm.expression} as {dm.name}" for dm in fact.derived_measures]

        # Dedup while preserving order — prevents duplicate columns when date_column
        # is also in dimension_keys (periodic snapshots) or measures.
        seen_col_keys: set[str] = set()
        deduped_all_cols: list[str] = []
        for _c in fact.dimension_keys + extra_pk + date_cols + fact.measures + derived_cols:
            # Normalise aliases ("table.col as alias" → "alias") for dedup key.
            _key = _c.split(" as ")[-1].strip() if " as " in _c else _c.split(".")[-1].strip()
            if _key not in seen_col_keys:
                seen_col_keys.add(_key)
                deduped_all_cols.append(_c)
        cols = format_columns(deduped_all_cols)

        if join_clause:
            from_clause = f"{{{{ ref('stg_{fact_src_schema}_{fact.source_table}') }}}} fact_src\n{join_clause}"
        else:
            from_clause = f"{{{{ ref('stg_{fact_src_schema}_{fact.source_table}') }}}}"

        # Incremental materialization when an effective date is available.
        # Uses the shared incremental_date_filter macro so the lookback logic is
        # defined once and the window is globally configurable via dbt variables.
        effective_date_alias = fact_effective_dates.get(fact.name, "")
        if effective_date_alias:
            materialization = f"materialized='incremental', unique_key='{fact.name}_sk'"
            # max_col differs from filter_col when the date comes from a FK join
            # (filter_col is qualified "table.col"; max_col is the SELECT alias).
            if date_raw_expr != effective_date_alias:
                incr_block = (
                    f"{{{{ incremental_date_filter('{date_raw_expr}', '{effective_date_alias}') }}}}"
                )
            else:
                incr_block = f"{{{{ incremental_date_filter('{date_raw_expr}') }}}}"
        else:
            materialization = "materialized='table'"
            incr_block = ""

        sql = f"""-- Fact: {fact.name}
{{{{ config({materialization}) }}}}

select
    {{{{ dbt_utils.generate_surrogate_key(['{pk_str}']) }}}} as {fact.name}_sk,
{cols}
from {from_clause}
{incr_block}
"""
        (base / "models" / "silver" / "facts" / f"{fact.name}.sql").write_text(sql)
    
    # Gold models
    for gold in plan.gold:
        # Use effective date: may come from a FK-joined date injected into the fact model (Fix C).
        effective_date = gold.date_column or fact_effective_dates.get(gold.source_fact, "")

        grain_func = {
            "daily": "day", "day": "day",
            "monthly": "month", "month": "month",
            "yearly": "year", "year": "year",
            "weekly": "week", "week": "week",
        }.get(gold.grain.lower() if gold.grain else "", "day")

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

        if effective_date:
            date_line = f"    date_trunc('{grain_func}', {effective_date}) as {gold.grain}_date,"
        else:
            date_line = f"    -- TODO: add date column (none found on {gold.source_fact})"

        # Fix A: dynamic GROUP BY position tracking — positions shift when date is absent.
        select_pos = 1
        group_by_positions = []
        if effective_date:
            group_by_positions.append(str(select_pos))
            select_pos += 1
        for _ in gold.dimensions:
            group_by_positions.append(str(select_pos))
            select_pos += 1
        group_by = "group by " + ", ".join(group_by_positions) if group_by_positions else ""

        sql = f"""-- Gold: {gold.name}
-- {gold.description}
{{{{ config(materialized='table') }}}}

select
{date_line}
{chr(10).join(dims_sql)}
{(','+chr(10)).join(metrics_sql)}
from {{{{ ref('{gold.source_fact}') }}}}
{group_by}
"""
        (base / "models" / "gold" / f"{gold.name}.sql").write_text(sql)
    
    # Semantic Layer YAML
    if semantic_layer is not None:
        _write_semantic_layer(semantic_layer, base)
    
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