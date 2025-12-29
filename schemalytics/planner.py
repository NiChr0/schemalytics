"""Generate modeling plan from schema and context."""
from schemalytics.models import (
    Schema, BusinessContext, ModelingPlan,
    DimensionPlan, FactPlan, Table, GoldPlan, MetricDefinition
)
from schemalytics import llm

DATE_COLUMNS = {"created_at", "updated_at", "order_date", "date", "timestamp", "created", "modified"}
MEASURE_TYPES = {"INTEGER", "NUMERIC", "DECIMAL", "FLOAT", "DOUBLE", "MONEY", "REAL", "BIGINT"}


class TableClassification:
    """Classification result for a single table."""
    def __init__(self, table: Table, role: str, confidence: str, reason: str):
        self.table = table
        self.role = role  # "fact", "dimension", "bridge", "skip"
        self.confidence = confidence  # "high", "medium", "low"
        self.reason = reason


def build_fk_graph(schema: Schema) -> dict:
    """Build FK relationship graph."""
    graph = {t.name: {"outgoing": [], "incoming": []} for t in schema.tables}
    
    for table in schema.tables:
        for fk in table.foreign_keys:
            graph[table.name]["outgoing"].append(fk.references_table)
            if fk.references_table in graph:
                graph[fk.references_table]["incoming"].append(table.name)
    
    return graph


def classify_by_fk_graph(schema: Schema) -> list[TableClassification]:
    """Classify tables using FK graph analysis."""
    graph = build_fk_graph(schema)
    classifications = []
    
    for table in schema.tables:
        outgoing = len(graph[table.name]["outgoing"])
        incoming = len(graph[table.name]["incoming"])
        
        if outgoing >= 2 and incoming <= 1:
            role, conf = "fact", "high"
            reason = f"References {outgoing} tables, referenced by {incoming}"
        elif incoming >= 2 and outgoing <= 1:
            role, conf = "dimension", "high"
            reason = f"Referenced by {incoming} tables, references {outgoing}"
        elif outgoing >= 2 and incoming >= 2:
            role, conf = "bridge", "medium"
            reason = f"Many-to-many junction: {outgoing} out, {incoming} in"
        elif outgoing == 1 and incoming == 0:
            has_date = find_date_column(table.columns) is not None
            if has_date or find_measures(table.columns):
                role, conf = "fact", "medium"
                reason = "Single FK with date/measures"
            else:
                role, conf = "dimension", "low"
                reason = "Single FK, no date/measures"
        elif outgoing == 0 and incoming == 0:
            role, conf = "dimension", "low"
            reason = "No FK relationships"
        else:
            role, conf = "dimension", "low"
            reason = f"Ambiguous: {outgoing} out, {incoming} in"
        
        classifications.append(TableClassification(table, role, conf, reason))
    
    return classifications


def find_date_column(columns: list) -> str | None:
    """Find most likely date column."""
    for col in columns:
        if col.name.lower() in DATE_COLUMNS:
            return col.name
    for col in columns:
        if "date" in col.data_type.lower() or "timestamp" in col.data_type.lower():
            return col.name
    return None


def find_measures(columns: list) -> list[str]:
    """Find numeric columns likely to be measures."""
    return [
        col.name for col in columns
        if any(t in col.data_type.upper() for t in MEASURE_TYPES)
        and not col.name.endswith("_id") and col.name != "id"
    ]


def _infer_metric_type(column_name: str, data_type: str) -> str:
    """Infer aggregation type from column name and data type."""
    col_lower = column_name.lower()
    
    # Revenue/amount/price → SUM
    if any(word in col_lower for word in ["revenue", "amount", "price", "total", "sales", "cost"]):
        return "SUM"
    
    # Count/quantity → SUM (for totals) or COUNT
    if any(word in col_lower for word in ["quantity", "count", "units"]):
        return "SUM"
    
    # Rate/percentage → AVG
    if any(word in col_lower for word in ["rate", "percent", "ratio", "avg", "average"]):
        return "AVG"
    
    # Default numeric → SUM
    return "SUM"


def _create_time_aggregates(
    fact: FactPlan,
    grain: str,
    context: BusinessContext
) -> list[GoldPlan]:
    """Generate time-grain aggregates for a fact table."""
    aggregates = []
    
    # Determine grain function
    grain_func_map = {
        "daily": "day",
        "weekly": "week",
        "monthly": "month",
        "yearly": "year"
    }
    grain_func = grain_func_map.get(grain, "day")
    
    # Create metrics from fact measures
    metrics = []
    for measure in fact.measures:
        agg_type = _infer_metric_type(measure, "NUMERIC")
        metrics.append(MetricDefinition(
            name=f"{agg_type.lower()}_{measure}",
            aggregation=agg_type,
            column=measure,
            description=f"{agg_type} of {measure} by {grain}"
        ))
    
    # Add record count
    metrics.append(MetricDefinition(
        name="record_count",
        aggregation="COUNT",
        column="*",
        description=f"Count of records by {grain}"
    ))
    
    aggregates.append(GoldPlan(
        name=f"gold_{grain}_{fact.source_table}",
        source_fact=fact.name,
        grain=grain,
        dimensions=[],  # Time only for now
        metrics=metrics,
        date_column=fact.date_column,
        description=f"{grain.capitalize()} aggregation of {fact.name}"
    ))
    
    return aggregates


def _ecommerce_aggregates(
    fact: FactPlan,
    dimensions: list[DimensionPlan]
) -> list[GoldPlan]:
    """Generate ecommerce-specific aggregates."""
    aggregates = []
    
    # Revenue metrics by product/customer
    if "product" in fact.source_table.lower() or "order" in fact.source_table.lower():
        revenue_cols = [m for m in fact.measures if "amount" in m.lower() or "price" in m.lower()]
        
        if revenue_cols:
            metrics = [
                MetricDefinition(
                    name="total_revenue",
                    aggregation="SUM",
                    column=revenue_cols[0],
                    description="Total revenue"
                ),
                MetricDefinition(
                    name="order_count",
                    aggregation="COUNT",
                    column="*",
                    description="Number of orders"
                ),
                MetricDefinition(
                    name="avg_order_value",
                    aggregation="AVG",
                    column=revenue_cols[0],
                    description="Average order value"
                )
            ]
            
            aggregates.append(GoldPlan(
                name="gold_daily_sales_summary",
                source_fact=fact.name,
                grain="daily",
                dimensions=[],
                metrics=metrics,
                date_column=fact.date_column,
                description="Daily sales performance metrics"
            ))
    
    return aggregates


def _saas_aggregates(
    fact: FactPlan,
    dimensions: list[DimensionPlan]
) -> list[GoldPlan]:
    """Generate SaaS-specific aggregates."""
    aggregates = []
    
    # User activity metrics
    if "user" in fact.source_table.lower() or "event" in fact.source_table.lower():
        user_key = next((k for k in fact.dimension_keys if "user" in k.lower()), None)
        
        if user_key:
            metrics = [
                MetricDefinition(
                    name="active_users",
                    aggregation="COUNT_DISTINCT",
                    column=user_key,
                    description="Number of active users"
                ),
                MetricDefinition(
                    name="total_events",
                    aggregation="COUNT",
                    column="*",
                    description="Total event count"
                )
            ]
            
            aggregates.append(GoldPlan(
                name="gold_daily_user_activity",
                source_fact=fact.name,
                grain="daily",
                dimensions=[],
                metrics=metrics,
                date_column=fact.date_column,
                description="Daily active users and activity"
            ))
    
    return aggregates


def llm_suggest_gold_models(
    facts: list[FactPlan],
    dimensions: list[DimensionPlan],
    context: BusinessContext
) -> list[dict]:
    """Use LLM to suggest Gold models based on facts and business context."""
    facts_summary = [
        {
            "name": f.name,
            "source": f.source_table,
            "grain": f.grain,
            "measures": f.measures,
            "dimensions": f.dimension_keys,
            "date_column": f.date_column
        }
        for f in facts
    ]
    
    dims_summary = [
        {"name": d.name, "source": d.source_table}
        for d in dimensions
    ]
    
    prompt = f"""You are a data modeling expert. Suggest Gold layer aggregate models for this dimensional model.

Business Context:
- Type: {context.business_type}
- Goals: {', '.join(context.goals)}
- Temporal: {context.temporal}

Available Facts:
{facts_summary}

Available Dimensions:
{dims_summary}

Your task:
1. Suggest 3-5 Gold aggregate models that would be useful for analytics
2. Focus on common reporting patterns for {context.business_type}
3. Each should aggregate at least one fact table by time grain (daily/monthly/yearly)
4. Include appropriate metrics (SUM, COUNT, AVG, etc.)

Respond ONLY with JSON:
{{
  "gold_models": [
    {{
      "name": "gold_daily_revenue",
      "source_fact": "fct_orders",
      "grain": "daily",
      "dimensions": [],
      "metrics": [
        {{"name": "total_revenue", "aggregation": "SUM", "column": "amount", "description": "Total daily revenue"}},
        {{"name": "order_count", "aggregation": "COUNT", "column": "*", "description": "Number of orders"}}
      ],
      "date_column": "order_date",
      "description": "Daily revenue and order metrics"
    }}
  ]
}}"""

    try:
        print("  🤖 Generating Gold models with LLM...")
        response = llm.query_json(prompt)
        print("  ✓ LLM Gold suggestions received")
        return response.get("gold_models", [])
    except Exception as e:
        print(f"  ⚠️  LLM Gold generation failed: {e}")
        print("  ℹ️  Will use heuristic fallback")
        return []


def generate_gold_models(
    facts: list[FactPlan],
    dimensions: list[DimensionPlan],
    context: BusinessContext
) -> list[GoldPlan]:
    """Generate Gold aggregate models using LLM suggestions."""
    # Get LLM suggestions
    llm_suggestions = llm_suggest_gold_models(facts, dimensions, context)
    
    # Convert to GoldPlan objects
    gold_models = []
    for suggestion in llm_suggestions:
        try:
            metrics = [
                MetricDefinition(**m) for m in suggestion.get("metrics", [])
            ]
            gold_models.append(GoldPlan(
                name=suggestion["name"],
                source_fact=suggestion["source_fact"],
                grain=suggestion["grain"],
                dimensions=suggestion.get("dimensions", []),
                metrics=metrics,
                date_column=suggestion["date_column"],
                description=suggestion.get("description", "")
            ))
        except Exception as e:
            print(f"  ⚠️  Skipping invalid Gold model: {e}")
            continue
    
    # Fallback: Generate heuristic-based aggregates if LLM fails or returns too few
    if len(gold_models) < 2:
        print(f"  ℹ️  Using heuristic fallback for Gold models (got {len(gold_models)} from LLM)...")
        
        # Parse selected grains from context
        selected_grains = context.grain.split(",") if context.grain else ["daily", "monthly", "yearly"]
        
        for fact in facts:
            # Time aggregates - only generate user-selected grains
            for grain in selected_grains:
                gold_models.extend(_create_time_aggregates(fact, grain.strip(), context))
            
            # Business-specific aggregates
            if context.business_type.startswith("ecommerce"):
                gold_models.extend(_ecommerce_aggregates(fact, dimensions))
            elif context.business_type.startswith("saas"):
                gold_models.extend(_saas_aggregates(fact, dimensions))
        print(f"  ✓ Generated {len(gold_models)} Gold models using heuristics")
    else:
        print(f"  ✓ Generated {len(gold_models)} Gold models")
    
    return gold_models


def llm_validate_and_finalize(
    schema: Schema,
    classifications: list[TableClassification]
) -> list[dict]:
    """LLM reviews heuristic classifications and returns final validated plan."""
    schema_summary = [
        {
            "table": t.name,
            "columns": [c.name for c in t.columns],
            "fks": [f"{fk.column} -> {fk.references_table}" for fk in t.foreign_keys]
        }
        for t in schema.tables
    ]
    
    heuristic_plan = [
        {"table": c.table.name, "role": c.role, "confidence": c.confidence, "reason": c.reason}
        for c in classifications
    ]
    
    prompt = f"""You are a data modeling expert. Review these table classifications for building a dimensional model (star schema).

Database schema:
{schema_summary}

Heuristic classifications (from FK graph analysis):
{heuristic_plan}

Your task:
1. Review each classification
2. Confirm or correct the role (fact/dimension/bridge/skip)
3. Provide clear reasoning

Respond ONLY with JSON:
{{
  "tables": [
    {{"table": "name", "role": "fact|dimension|bridge|skip", "reason": "brief explanation"}}
  ]
}}"""

    try:
        print("  🤖 Validating with LLM...")
        response = llm.query_json(prompt)
        print("  ✓ LLM validation complete")
        return response.get("tables", [])
    except Exception as e:
        # If LLM fails, return heuristic results as-is
        print(f"  ⚠️  LLM validation failed: {e}")
        print("  ℹ️  Using heuristic classifications")
        return [{"table": c.table.name, "role": c.role, "reason": c.reason} for c in classifications]


def format_plan_for_review(
    heuristic: list[TableClassification],
    llm_final: list[dict],
    gold_models: list[GoldPlan] = None
) -> str:
    """Format plan for user review."""
    lines = [
        "",
        "=" * 60,
        "PROPOSED DATA MODEL",
        "=" * 60,
        "",
        f"{'Table':<25} {'Role':<12} {'Reason'}",
        "-" * 60,
    ]
    
    for item in llm_final:
        role = item["role"].upper()
        lines.append(f"{item['table']:<25} {role:<12} {item['reason']}")
    
    if gold_models:
        lines.extend([
            "",
            "=" * 60,
            "GOLD LAYER AGGREGATES",
            "=" * 60,
            "",
        ])
        for gold in gold_models:
            lines.append(f"- {gold.name} ({gold.grain})")
            lines.append(f"  Source: {gold.source_fact}")
            lines.append(f"  Metrics: {', '.join(m.name for m in gold.metrics)}")
            lines.append("")
    
    lines.append("")
    return "\n".join(lines)


def build_plan_from_llm_output(
    schema: Schema,
    llm_output: list[dict],
    context: BusinessContext
) -> ModelingPlan:
    """Convert LLM's final classifications to ModelingPlan."""
    table_lookup = {t.name: t for t in schema.tables}
    role_map = {item["table"]: item["role"] for item in llm_output}
    
    bronze = list(role_map.keys())
    dimensions = []
    facts = []
    
    print(f"\n  Building plan from {len(role_map)} tables...")
    
    for table_name, role in role_map.items():
        if role == "skip":
            continue
            
        table = table_lookup.get(table_name)
        if not table:
            continue
        
        if role == "dimension":
            dimensions.append(DimensionPlan(
                name=f"dim_{table_name}",
                source_table=table_name,
                scd_type=2 if context.temporal == "historical" else 1,
                grain=f"One row per {table_name.rstrip('s')}",
                columns=[col.name for col in table.columns],
            ))
        
        elif role in ("fact", "bridge"):
            date_col = find_date_column(table.columns)
            measures = find_measures(table.columns)
            dim_keys = [fk.column for fk in table.foreign_keys]
            
            facts.append(FactPlan(
                name=f"fct_{table_name}",
                source_table=table_name,
                grain=f"One row per {table_name.rstrip('s')}",
                dimension_keys=dim_keys,
                measures=measures,
                date_column=date_col or "created_at",
            ))
    
    print(f"  ✓ Classified: {len(dimensions)} dimensions, {len(facts)} facts")
    
    # Generate Gold models
    gold_models = generate_gold_models(facts, dimensions, context)
    
    return ModelingPlan(bronze=bronze, dimensions=dimensions, facts=facts, gold=gold_models)


def generate_plan(schema: Schema, context: BusinessContext) -> ModelingPlan:
    """Generate plan using heuristics only (no LLM)."""
    classifications = classify_by_fk_graph(schema)
    llm_output = [{"table": c.table.name, "role": c.role, "reason": c.reason} for c in classifications]
    return build_plan_from_llm_output(schema, llm_output, context)


def generate_plan_with_validation(
    schema: Schema,
    context: BusinessContext
) -> tuple[ModelingPlan, list[TableClassification], list[dict], str]:
    """
    Full pipeline: heuristics → LLM validation → Gold generation → formatted review.
    Returns (plan, heuristic_classifications, llm_output, review_text)
    """
    # Step 1: Heuristic classification
    heuristic = classify_by_fk_graph(schema)
    
    # Step 2: LLM validates and finalizes
    llm_output = llm_validate_and_finalize(schema, heuristic)
    
    # Step 3: Build plan from LLM output (includes Gold generation)
    plan = build_plan_from_llm_output(schema, llm_output, context)
    
    # Step 4: Format for user review (include Gold models)
    review_text = format_plan_for_review(heuristic, llm_output, plan.gold)
    
    return plan, heuristic, llm_output, review_text