"""Generate modeling plan from schema and context."""
from schemalytics.models import (
    Schema, BusinessContext, ModelingPlan,
    DimensionPlan, FactPlan, Table
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
        response = llm.query_json(prompt)
        return response.get("tables", [])
    except Exception as e:
        # If LLM fails, return heuristic results as-is
        return [{"table": c.table.name, "role": c.role, "reason": c.reason} for c in classifications]


def format_plan_for_review(
    heuristic: list[TableClassification],
    llm_final: list[dict]
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
    
    return ModelingPlan(bronze=bronze, dimensions=dimensions, facts=facts)


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
    Full pipeline: heuristics → LLM validation → formatted review.
    Returns (plan, heuristic_classifications, llm_output, review_text)
    """
    # Step 1: Heuristic classification
    heuristic = classify_by_fk_graph(schema)
    
    # Step 2: LLM validates and finalizes
    llm_output = llm_validate_and_finalize(schema, heuristic)
    
    # Step 3: Format for user review
    review_text = format_plan_for_review(heuristic, llm_output)
    
    # Step 4: Build final plan from LLM output
    plan = build_plan_from_llm_output(schema, llm_output, context)
    
    return plan, heuristic, llm_output, review_text
