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


def gather_context_interactively(schema: Schema) -> BusinessContext:
    """Gather business context through interactive prompts."""
    from schemalytics.industry_taxonomy import INDUSTRY_TAXONOMY
    
    print("\n" + "=" * 80)
    print("BUSINESS CONTEXT GATHERING")
    print("=" * 80)
    
    # Industry selection
    print("\n📊 SELECT YOUR INDUSTRY:")
    industries = [(key, data["name"]) for key, data in INDUSTRY_TAXONOMY.items()]
    
    for i, (key, name) in enumerate(industries, 1):
        print(f"{i}. {name}")
    
    industry_choice = input(f"\nEnter number (1-{len(industries)}): ").strip()
    try:
        industry_idx = int(industry_choice) - 1
        if 0 <= industry_idx < len(industries):
            industry_key, industry_name = industries[industry_idx]
        else:
            industry_key = "other"
            industry_name = "Other/Custom"
    except ValueError:
        industry_key = "other"
        industry_name = "Other/Custom"
    
    # Sub-industry selection
    print(f"\n📋 SELECT SUB-INDUSTRY FOR {industry_name.upper()}:")
    
    sub_industries_data = INDUSTRY_TAXONOMY[industry_key]["sub_industries"]
    sub_industries = [(key, data["name"]) for key, data in sub_industries_data.items()]
    
    for i, (key, name) in enumerate(sub_industries, 1):
        print(f"{i}. {name}")
    
    sub_choice = input(f"\nEnter number (1-{len(sub_industries)}, default 1): ").strip() or "1"
    try:
        sub_idx = int(sub_choice) - 1
        if 0 <= sub_idx < len(sub_industries):
            sub_key, sub_name = sub_industries[sub_idx]
        else:
            sub_key, sub_name = sub_industries[0]
    except ValueError:
        sub_key, sub_name = sub_industries[0]
    
    business_type = f"{industry_key}_{sub_key}"
    
    # Get suggested entities and goals from taxonomy
    sub_data = sub_industries_data[sub_key]
    suggested_entities = sub_data.get("entities", [])
    suggested_goals = sub_data.get("goals", [])
    
    # Entities
    print("\n📋 KEY ENTITIES (comma-separated):")
    print(f"Suggested for {sub_name}: {', '.join(suggested_entities[:5])}")
    print(f"Detected tables: {', '.join([t.name for t in schema.tables[:5]])}")
    entities_input = input("Enter entities (or press Enter to use suggestions): ").strip()
    if entities_input:
        entities = [e.strip() for e in entities_input.split(",")]
    elif suggested_entities:
        entities = suggested_entities
    else:
        entities = [t.name for t in schema.tables]
    
    # Goals
    print("\n🎯 ANALYTICAL GOALS:")
    print(f"Suggested for {sub_name}: {', '.join(suggested_goals[:3])}")
    goals_input = input("Enter goals (comma-separated, or press Enter to use suggestions): ").strip()
    if goals_input:
        goals = [g.strip() for g in goals_input.split(",")]
    elif suggested_goals:
        goals = suggested_goals
    else:
        goals = ["reporting", "analytics"]
    
    # Temporal
    print("\n⏰ HISTORICAL TRACKING:")
    print("1. Snapshot (current state only)")
    print("2. Historical (track changes over time)")
    temporal_choice = input("Enter number (1-2, default 2): ").strip() or "2"
    temporal = "snapshot" if temporal_choice == "1" else "historical"
    
    # Time grains
    print("\n📅 TIME GRAINS FOR AGGREGATIONS:")
    print("Options: daily, weekly, monthly, yearly")
    grain_input = input("Enter grains (comma-separated, default: daily,monthly): ").strip()
    grain = grain_input if grain_input else "daily,monthly"
    
    print("\n✓ Context gathered successfully")
    print(f"  Industry: {business_type}")
    print(f"  Entities: {', '.join(entities[:3])}...")
    print(f"  Goals: {', '.join(goals[:3])}...")
    
    return BusinessContext(
        business_type=business_type,
        entities=entities,
        goals=goals,
        temporal=temporal,
        grain=grain
    )


def classify_by_fk_graph(schema: Schema) -> list[TableClassification]:
    """Classify tables as fact/dimension/bridge using FK graph analysis."""
    
    classifications = []
    
    # Build FK graph
    incoming_fks = {}  # table -> count of tables referencing it
    outgoing_fks = {}  # table -> count of tables it references
    
    for table in schema.tables:
        table_name = table.name
        outgoing_fks[table_name] = len(table.foreign_keys)
        
        # Count incoming FKs
        if table_name not in incoming_fks:
            incoming_fks[table_name] = 0
        
        for fk in table.foreign_keys:
            ref_table = fk.references_table
            incoming_fks[ref_table] = incoming_fks.get(ref_table, 0) + 1
    
    # Classify based on FK patterns
    for table in schema.tables:
        name = table.name
        incoming = incoming_fks.get(name, 0)
        outgoing = outgoing_fks.get(name, 0)
        
        # Heuristics
        if outgoing >= 2 and incoming == 0:
            # Many outgoing, no incoming -> likely FACT
            role = "fact"
            confidence = "high"
            reason = f"Has {outgoing} outgoing FKs, no incoming FKs (references dimensions)"
        elif incoming >= 2 and outgoing == 0:
            # Many incoming, no outgoing -> likely DIMENSION
            role = "dimension"
            confidence = "high"
            reason = f"Has {incoming} incoming FKs, no outgoing FKs (referenced by facts)"
        elif outgoing >= 1 and incoming >= 1:
            # Both incoming and outgoing -> could be BRIDGE or FACT
            if outgoing > incoming:
                role = "fact"
                confidence = "medium"
                reason = f"Has {outgoing} outgoing and {incoming} incoming FKs (likely fact)"
            else:
                role = "bridge"
                confidence = "medium"
                reason = f"Has {outgoing} outgoing and {incoming} incoming FKs (likely bridge table)"
        elif outgoing == 1 and incoming == 0:
            # Single FK, no incoming -> could be DIMENSION or FACT
            role = "dimension"
            confidence = "low"
            reason = f"Has 1 outgoing FK, no incoming (ambiguous - assuming dimension)"
        elif outgoing == 0 and incoming == 1:
            # No outgoing, single incoming -> likely DIMENSION
            role = "dimension"
            confidence = "medium"
            reason = f"No outgoing FKs, 1 incoming FK (likely dimension)"
        else:
            # No FKs at all -> likely DIMENSION (standalone lookup table)
            role = "dimension"
            confidence = "low"
            reason = "No foreign keys (standalone table - assuming dimension)"
        
        classifications.append(TableClassification(
            table=table,
            role=role,
            confidence=confidence,
            reason=reason
        ))
    
    return classifications


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
    
    # Get all source table names for bronze layer
    all_source_tables = [t.name for t in schema.tables]
    
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

CRITICAL: The bronze array MUST include ALL source tables from the database.
All source tables: {all_source_tables}
Do NOT skip any tables. Every table in the database needs a bronze staging model.

Your task: Create a DETAILED plan with EXACT specifications:

1. Bronze layer: List all source tables (passthrough views)
   - In the "bronze" array, provide ONLY the base table names (e.g., "customers", "orders")
   - Do NOT include the "stg_" prefix in the bronze array
   - The schema name goes in "bronze_schema" field
   - Example: {{"bronze": ["customers", "orders"], "bronze_schema": "public"}}
   - These will be displayed as: stg_public_customers, stg_public_orders
   
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
   - Exact table name (agg_<grain>_<metric>)
   - Source fact table
   - Time grain (daily/weekly/monthly/yearly)
   - Metrics with aggregation type (SUM/COUNT/AVG)
   - Description

CRITICAL: Ensure every "source_table" referenced in dimensions or facts exists in the "bronze" array.
For example, if you create fct_order_details with source_table="order_details", then "order_details" must be in the bronze array.

Respond ONLY with JSON:
{{
  "bronze": ["customers", "orders", ...],
  "bronze_schema": "public",
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
      "name": "agg_daily_revenue",
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
        
        # Validate bronze coverage
        bronze_tables = set(response.get("bronze", []))
        missing_bronze = set(all_source_tables) - bronze_tables
        
        if missing_bronze:
            print(f"  ⚠️  Warning: Adding missing bronze tables: {', '.join(missing_bronze)}")
            response["bronze"] = list(bronze_tables.union(missing_bronze))
        
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
    bronze_schema = plan_dict.get("bronze_schema", "public")
    for table in bronze:
        # Check if table already has stg_ prefix (LLM might include it)
        if table.startswith("stg_"):
            print(f"  • {table}")
        else:
            print(f"  • stg_{bronze_schema}_{table}")
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
    
    # Get all source table names for validation
    all_source_tables = [t.name for t in schema.tables]
    
    prompt = f"""You are a data modeling expert. Interpret user feedback and amend the data model plan.

Current plan:
{current_plan}

Database schema (for reference):
{schema_summary}

All source tables that MUST be in bronze: {all_source_tables}

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
5. ENSURE the bronze array includes ALL source tables: {all_source_tables}
6. SELF-CHECK before responding:
   - If feedback asks to "change X to Y": verify X is removed AND Y is added
   - If feedback asks to "delete X": verify X is completely removed
   - If feedback asks to "add X": verify X exists in the new plan
   - If feedback asks to "move X from A to B": verify X removed from A and added to B
   - Compare the current plan to your new plan and confirm changes match the feedback

Examples of feedback interpretation:
- "make orders weekly" → Change agg_daily_orders to agg_weekly_orders (remove daily, add weekly)
- "split customers by type" → Create dim_customers_b2b and dim_customers_b2c (remove dim_customers)
- "add customer lifetime value" → Add new gold metric with CLV calculation (name: agg_customer_ltv)
- "remove product dimension" → Remove dim_products completely, update all facts that reference it
- "change X to Y" → REMOVE X completely from plan, ADD Y as replacement, update all FK references to point to Y
- "change dim_orders to fct_orders" → REMOVE dim_orders from dimensions, ADD fct_orders to facts with appropriate grain/measures
- "delete dim_orders and create fct_orders" → REMOVE dim_orders from dimensions, ADD fct_orders to facts
- "delete X" → REMOVE X completely from the appropriate section (dimensions/facts/gold)

CRITICAL PRINCIPLES FOR MODIFICATIONS:

1. **CHANGE operations** ("change X to Y", "convert X to Y", "make X a Y"):
   - REMOVE the original (X) completely from its current section
   - ADD the replacement (Y) to the appropriate section
   - Verify: X should NOT exist in final plan, Y SHOULD exist
   
2. **DELETE operations** ("delete X", "remove X", "drop X"):
   - REMOVE the item completely from all sections
   - Update any references to the deleted item
   - Verify: X should NOT exist anywhere in final plan
   
3. **ADD operations** ("add X", "create X", "include X"):
   - ADD the new item to the appropriate section
   - Verify: X SHOULD exist in final plan
   
4. **COMBINED operations** ("delete X and create Y", "remove X, add Y"):
   - Execute BOTH operations: remove X AND add Y
   - Verify: X should NOT exist, Y SHOULD exist

5. **MOVE operations** ("X should be a fact not dimension"):
   - Identify where X currently is (dimensions/facts/gold)
   - REMOVE from current location
   - ADD to target location with appropriate structure
   - Verify: X exists in new location, not in old location

ALWAYS output the COMPLETE plan with ALL modifications applied.
Do NOT return a partial plan or just the changes.

NAMING CONVENTIONS:
- Bronze models: stg_<schema>_<table> (e.g., stg_public_customers)
- Silver dimensions: dim_<entity> (e.g., dim_customers)
- Silver facts: fct_<entity> (e.g., fct_orders)
- Gold aggregates: agg_<grain>_<metric> (e.g., agg_daily_revenue)

CRITICAL VALIDATION RULE:
Every table referenced as "source_table" in dimensions or facts MUST exist in the "bronze" array.
Example: If fct_order_details has "source_table": "order_details", then "order_details" MUST be in the bronze array.
If user says "you're missing stg_X model", add the base table name (X without stg_schema_ prefix) to the bronze array.

EXAMPLE: "you are missing a stg_order_details model"
  → Add "order_details" to bronze array
  → Result: bronze array includes "order_details"

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
        
        # Validate bronze coverage
        bronze_tables = set(response.get("bronze", []))
        missing_bronze = set(all_source_tables) - bronze_tables
        
        if missing_bronze:
            print(f"  ⚠️  Warning: Adding missing bronze tables: {', '.join(missing_bronze)}")
            response["bronze"] = list(bronze_tables.union(missing_bronze))
        
        # Dynamic validation: Check if plan actually changed
        def plan_changed(old_plan, new_plan):
            """Check if any meaningful changes were made."""
            old_dims = set(d['name'] for d in old_plan.get('silver', {}).get('dimensions', []))
            new_dims = set(d['name'] for d in new_plan.get('silver', {}).get('dimensions', []))
            
            old_facts = set(f['name'] for f in old_plan.get('silver', {}).get('facts', []))
            new_facts = set(f['name'] for f in new_plan.get('silver', {}).get('facts', []))
            
            old_gold = set(g['name'] for g in old_plan.get('gold', []))
            new_gold = set(g['name'] for g in new_plan.get('gold', []))
            
            return (old_dims != new_dims or 
                    old_facts != new_facts or 
                    old_gold != new_gold or
                    old_plan.get('bronze') != new_plan.get('bronze'))
        
        if not plan_changed(current_plan, response):
            print(f"  ⚠️  Warning: No changes detected in plan after feedback: '{feedback}'")
            print(f"  The LLM may not have understood the request. Try rephrasing.")
        
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