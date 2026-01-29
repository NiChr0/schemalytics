"""Enhanced planner with interactive refinement loop."""
from schemalytics.models import (
    Schema, BusinessContext, ModelingPlan,
    DimensionPlan, FactPlan, GoldPlan, MetricDefinition, Table
)
from schemalytics import llm
from typing import Any


class TableClassification:
    """Classification result for a single table."""
    def __init__(self, table: Table, role: str, confidence: str, reason: str):
        self.table = table
        self.role = role
        self.confidence = confidence
        self.reason = reason


def llm_generate_detailed_plan(
    schema: Schema,
    context: BusinessContext,
    heuristic_classifications: list[TableClassification]
) -> dict:
    """Generate detailed concrete plan with exact table names, types, grains, FKs, measures."""
    
    schema_summary = []
    for t in schema.tables:
        schema_summary.append({
            "table": t.name,
            "columns": [{"name": c.name, "type": c.data_type} for c in t.columns],
            "primary_key": t.primary_key,
            "foreign_keys": [
                {"column": fk.column, "references": fk.references_table, "ref_column": fk.references_column}
                for fk in t.foreign_keys
            ]
        })
    
    heuristic_plan = [
        {"table": c.table.name, "role": c.role, "reason": c.reason}
        for c in heuristic_classifications
    ]
    
    prompt = f"""You are a data modeling expert. Generate a CONCRETE, DETAILED data modeling plan.

Database schema:
{schema_summary}

Initial classifications:
{heuristic_plan}

Business context:
- Industry: {context.business_type}
- Entities: {context.entities}
- Goals: {context.goals}
- Temporal: {context.temporal}
- Time grains: {context.grain}

Your task: Create a DETAILED plan with EXACT specifications:

1. Bronze layer: List all source tables (passthrough views)
2. Silver dimensions: For each dimension specify:
   - Exact table name (dim_<entity>)
   - SCD type (1 or 2 based on temporal={context.temporal})
   - Grain (e.g., "one row per customer")
   - Key columns (primary key, natural key)
   - All attribute columns to include
   
3. Silver facts: For each fact specify:
   - Exact table name (fct_<entity>)
   - Grain (e.g., "one row per order line")
   - Date column (which column to use for time)
   - Foreign keys with EXACT references (e.g., "customer_id -> dim_customers")
   - Measure columns (numeric columns to aggregate)
   
4. Gold aggregates: For each time grain ({context.grain}) specify:
   - Exact table name (gold_<grain>_<metric>)
   - Source fact table
   - Time grain (daily/weekly/monthly/yearly)
   - Metrics with aggregation type (SUM/COUNT/AVG)
   - Description

Respond ONLY with JSON:
{{
  "bronze": ["table1", "table2", ...],
  "silver": {{
    "dimensions": [
      {{
        "name": "dim_customers",
        "source_table": "customers",
        "scd_type": 2,
        "grain": "one row per customer per valid period",
        "primary_key": "customer_id",
        "columns": ["customer_id", "name", "email", "segment"]
      }}
    ],
    "facts": [
      {{
        "name": "fct_orders",
        "source_table": "orders",
        "grain": "one row per order",
        "date_column": "order_date",
        "foreign_keys": [
          {{"column": "customer_id", "references": "dim_customers"}},
          {{"column": "store_id", "references": "dim_stores"}}
        ],
        "measures": ["total_amount", "discount_amount", "tax_amount"]
      }}
    ]
  }},
  "gold": [
    {{
      "name": "gold_daily_revenue",
      "source_fact": "fct_orders",
      "grain": "daily",
      "date_column": "order_date",
      "metrics": [
        {{"name": "total_revenue", "aggregation": "SUM", "column": "total_amount"}},
        {{"name": "order_count", "aggregation": "COUNT", "column": "*"}}
      ],
      "description": "Daily revenue and order volume metrics"
    }}
  ]
}}"""

    try:
        print("\n  🤖 Generating detailed plan with LLM...")
        response = llm.query_json(prompt)
        print("  ✓ Detailed plan generated")
        return response
    except Exception as e:
        print(f"  ⚠️  LLM detailed plan failed: {e}")
        raise


def display_concrete_plan(plan_dict: dict) -> None:
    """Display concrete plan with exact table names, types, grains, FKs."""
    
    print("\n" + "=" * 80)
    print("CONCRETE DATA MODEL PLAN")
    print("=" * 80)
    
    # Bronze
    print("\n📦 BRONZE LAYER (Raw passthrough)")
    print("-" * 80)
    bronze = plan_dict.get("bronze", [])
    for table in bronze:
        print(f"  • bronze_{table}")
    print(f"\nTotal: {len(bronze)} tables (materialized as views)")
    
    # Silver - Dimensions
    print("\n" + "=" * 80)
    print("🔷 SILVER LAYER - DIMENSIONS")
    print("=" * 80)
    dimensions = plan_dict.get("silver", {}).get("dimensions", [])
    for dim in dimensions:
        print(f"\n{dim['name']} (SCD Type {dim['scd_type']})")
        print(f"  Source: {dim['source_table']}")
        print(f"  Grain: {dim['grain']}")
        print(f"  Columns: {', '.join(dim.get('columns', [])[:8])}")
        if len(dim.get('columns', [])) > 8:
            print(f"           ... and {len(dim['columns']) - 8} more")
    print(f"\nTotal: {len(dimensions)} dimension tables")
    
    # Silver - Facts
    print("\n" + "=" * 80)
    print("📊 SILVER LAYER - FACTS")
    print("=" * 80)
    facts = plan_dict.get("silver", {}).get("facts", [])
    for fact in facts:
        print(f"\n{fact['name']}")
        print(f"  Source: {fact['source_table']}")
        print(f"  Grain: {fact['grain']}")
        print(f"  Date: {fact['date_column']}")
        print(f"  Foreign Keys:")
        for fk in fact.get('foreign_keys', []):
            print(f"    → {fk['column']} → {fk['references']}")
        print(f"  Measures: {', '.join(fact.get('measures', []))}")
    print(f"\nTotal: {len(facts)} fact tables")
    
    # Gold
    print("\n" + "=" * 80)
    print("🥇 GOLD LAYER - PRE-AGGREGATED METRICS")
    print("=" * 80)
    gold = plan_dict.get("gold", [])
    
    # Group by grain
    by_grain = {}
    for g in gold:
        grain = g['grain']
        if grain not in by_grain:
            by_grain[grain] = []
        by_grain[grain].append(g)
    
    for grain, models in sorted(by_grain.items()):
        print(f"\n{grain.upper()} AGGREGATES ({len(models)} tables):")
        for g in models:
            print(f"\n  {g['name']}")
            print(f"    Source: {g['source_fact']}")
            print(f"    Description: {g['description']}")
            print(f"    Metrics:")
            for m in g.get('metrics', []):
                print(f"      • {m['name']} = {m['aggregation']}({m['column']})")
    
    print("\n" + "=" * 80)


def llm_refine_plan(
    current_plan: dict,
    feedback: str,
    schema: Schema,
    context: BusinessContext
) -> dict:
    """LLM interprets natural language feedback and amends the plan."""
    
    schema_summary = []
    for t in schema.tables:
        schema_summary.append({
            "table": t.name,
            "columns": [c.name for c in t.columns],
            "foreign_keys": [
                {"column": fk.column, "references": fk.references_table}
                for fk in t.foreign_keys
            ]
        })
    
    prompt = f"""You are a data modeling expert. Interpret user feedback and amend the data model plan.

Current plan:
{current_plan}

Database schema (for reference):
{schema_summary}

Business context:
- Industry: {context.business_type}
- Entities: {context.entities}
- Goals: {context.goals}

User feedback: "{feedback}"

Your task:
1. Interpret the feedback (even if informal/vague)
2. Validate if the change makes sense
3. If it doesn't make sense, suggest alternatives
4. Output the COMPLETE amended plan (not just changes)

Examples of feedback interpretation:
- "make orders weekly" → Change gold_daily_orders to gold_weekly_orders
- "split customers by type" → Create dim_customers_b2b and dim_customers_b2c
- "add customer lifetime value" → Add gold metric with CLV calculation
- "remove product dimension" → Remove dim_products, update facts accordingly

If the feedback is unclear or impossible, add a "validation" field explaining the issue.

Respond ONLY with JSON in the SAME format as current plan:
{{
  "validation": "OK" or "explanation of issue",
  "bronze": [...],
  "silver": {{
    "dimensions": [...],
    "facts": [...]
  }},
  "gold": [...]
}}"""

    try:
        print("\n  🤖 Interpreting feedback and refining plan...")
        response = llm.query_json(prompt)
        
        # Check validation
        if response.get("validation") != "OK":
            print(f"\n  ⚠️  Validation issue: {response.get('validation')}")
            print("  Please clarify your feedback or type 'skip' to keep current plan.")
            return current_plan
        
        print("  ✓ Plan refined")
        return response
    
    except Exception as e:
        print(f"  ⚠️  LLM refinement failed: {e}")
        return current_plan


def show_diff(old_plan: dict, new_plan: dict) -> None:
    """Show what changed between two plans."""
    
    print("\n" + "=" * 80)
    print("CHANGES IN THIS ITERATION")
    print("=" * 80)
    
    changes = []
    
    # Check bronze changes
    old_bronze = set(old_plan.get("bronze", []))
    new_bronze = set(new_plan.get("bronze", []))
    
    for table in new_bronze - old_bronze:
        changes.append(f"  ✓ Added bronze table: {table}")
    for table in old_bronze - new_bronze:
        changes.append(f"  ✗ Removed bronze table: {table}")
    
    # Check dimension changes
    old_dims = {d['name']: d for d in old_plan.get("silver", {}).get("dimensions", [])}
    new_dims = {d['name']: d for d in new_plan.get("silver", {}).get("dimensions", [])}
    
    for name in set(new_dims.keys()) - set(old_dims.keys()):
        changes.append(f"  ✓ Added dimension: {name}")
    for name in set(old_dims.keys()) - set(new_dims.keys()):
        changes.append(f"  ✗ Removed dimension: {name}")
    for name in set(old_dims.keys()) & set(new_dims.keys()):
        if old_dims[name] != new_dims[name]:
            changes.append(f"  ⟳ Modified dimension: {name}")
    
    # Check fact changes
    old_facts = {f['name']: f for f in old_plan.get("silver", {}).get("facts", [])}
    new_facts = {f['name']: f for f in new_plan.get("silver", {}).get("facts", [])}
    
    for name in set(new_facts.keys()) - set(old_facts.keys()):
        changes.append(f"  ✓ Added fact: {name}")
    for name in set(old_facts.keys()) - set(new_facts.keys()):
        changes.append(f"  ✗ Removed fact: {name}")
    for name in set(old_facts.keys()) & set(new_facts.keys()):
        if old_facts[name] != new_facts[name]:
            changes.append(f"  ⟳ Modified fact: {name}")
    
    # Check gold changes
    old_gold = {g['name']: g for g in old_plan.get("gold", [])}
    new_gold = {g['name']: g for g in new_plan.get("gold", [])}
    
    for name in set(new_gold.keys()) - set(old_gold.keys()):
        changes.append(f"  ✓ Added gold aggregate: {name}")
    for name in set(old_gold.keys()) - set(new_gold.keys()):
        changes.append(f"  ✗ Removed gold aggregate: {name}")
    for name in set(old_gold.keys()) & set(new_gold.keys()):
        if old_gold[name] != new_gold[name]:
            changes.append(f"  ⟳ Modified gold aggregate: {name}")
    
    if not changes:
        print("\n  (No changes detected)")
    else:
        print()
        for change in changes:
            print(change)
    
    print("\n" + "=" * 80)


def convert_plan_dict_to_modeling_plan(plan_dict: dict) -> ModelingPlan:
    """Convert LLM JSON plan to ModelingPlan Pydantic object."""
    
    # Convert dimensions
    dimensions = []
    for dim in plan_dict.get("silver", {}).get("dimensions", []):
        dimensions.append(DimensionPlan(
            name=dim["name"],
            source_table=dim["source_table"],
            scd_type=dim["scd_type"],
            grain=dim["grain"],
            columns=dim.get("columns", [])
        ))
    
    # Convert facts
    facts = []
    for fact in plan_dict.get("silver", {}).get("facts", []):
        # Extract FK column names
        fk_columns = [fk["column"] for fk in fact.get("foreign_keys", [])]
        
        facts.append(FactPlan(
            name=fact["name"],
            source_table=fact["source_table"],
            grain=fact["grain"],
            dimension_keys=fk_columns,
            measures=fact.get("measures", []),
            date_column=fact["date_column"]
        ))
    
    # Convert gold
    gold_models = []
    for gold in plan_dict.get("gold", []):
        metrics = []
        for m in gold.get("metrics", []):
            metrics.append(MetricDefinition(
                name=m["name"],
                aggregation=m["aggregation"],
                column=m["column"],
                description=m.get("description", f"{m['aggregation']} of {m['column']}")
            ))
        
        gold_models.append(GoldPlan(
            name=gold["name"],
            source_fact=gold["source_fact"],
            grain=gold["grain"],
            dimensions=gold.get("dimensions", []),
            metrics=metrics,
            date_column=gold["date_column"],
            description=gold["description"]
        ))
    
    return ModelingPlan(
        bronze=plan_dict.get("bronze", []),
        dimensions=dimensions,
        facts=facts,
        gold=gold_models
    )


def interactive_refinement_loop(
    schema: Schema,
    context: BusinessContext,
    heuristic_classifications: list[TableClassification]
) -> ModelingPlan | None:
    """Interactive loop: generate detailed plan → show → refine based on NL feedback → repeat until approved."""
    
    # Generate initial detailed plan
    plan_dict = llm_generate_detailed_plan(schema, context, heuristic_classifications)
    
    iteration = 1
    
    while True:
        print(f"\n{'='*80}")
        print(f"ITERATION {iteration}")
        print(f"{'='*80}")
        
        # Display concrete plan
        display_concrete_plan(plan_dict)
        
        # Get user feedback
        print("\n" + "=" * 80)
        print("FEEDBACK OPTIONS")
        print("=" * 80)
        print("  • Type natural language feedback to refine the plan")
        print("  • Examples:")
        print("    - 'make orders weekly instead of daily'")
        print("    - 'split customers into B2B and B2C dimensions'")
        print("    - 'add a metric for customer lifetime value'")
        print("    - 'remove the product dimension'")
        print("  • Type 'approve' or 'done' to accept the plan")
        print("  • Type 'reject' or 'cancel' to abort")
        print("=" * 80)
        
        feedback = input("\nYour feedback: ").strip()
        
        # Check for approval/rejection
        if feedback.lower() in ['approve', 'done', 'looks good', 'accept', 'yes']:
            print("\n✓ Plan approved! Generating dbt project...")
            return convert_plan_dict_to_modeling_plan(plan_dict)
        
        if feedback.lower() in ['reject', 'cancel', 'abort', 'quit', 'exit']:
            print("\n✗ Plan rejected. Aborting.")
            return None
        
        if not feedback:
            print("\n⚠️  Empty feedback. Please provide feedback or type 'approve'/'reject'.")
            continue
        
        # Refine plan based on feedback
        old_plan = plan_dict.copy()
        plan_dict = llm_refine_plan(plan_dict, feedback, schema, context)
        
        # Show diff
        show_diff(old_plan, plan_dict)
        
        iteration += 1