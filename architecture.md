# Interactive Refinement Architecture

## System Overview

```
┌─────────────────────────────────────────────────────────────────┐
│                    SCHEMALYTICS v0.2.0                          │
│              Interactive Data Model Generation                  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              │ User runs: schemalytics generate
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: EXTRACT SCHEMA                                         │
│  ────────────────────────                                       │
│  • SQLAlchemy connects to PostgreSQL                            │
│  • Extracts tables, columns, PKs, FKs                           │
│  • Returns Schema object                                        │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: GATHER CONTEXT                                         │
│  ───────────────────────                                        │
│  • Interactive prompts OR context.yaml                          │
│  • Industry selection (14+ industries)                          │
│  • Entities, goals, temporal, grains                            │
│  • Returns BusinessContext object                               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: HEURISTIC CLASSIFICATION                               │
│  ─────────────────────────────────                              │
│  • FK graph analysis                                            │
│  • Classify tables as fact/dimension/bridge                     │
│  • Returns list[TableClassification]                            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┏━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┓
┃  STEP 4: INTERACTIVE REFINEMENT LOOP  ★ NEW IN v0.2.0 ★       ┃
┃  ────────────────────────────────────                          ┃
┃                                                                 ┃
┃  ┌───────────────────────────────────────────────────────────┐ ┃
┃  │ 4a. LLM GENERATE DETAILED PLAN                            │ ┃
┃  │ ──────────────────────────────                            │ ┃
┃  │ Function: llm_generate_detailed_plan()                    │ ┃
┃  │                                                            │ ┃
┃  │ Input:                                                     │ ┃
┃  │   • Schema (tables, columns, FKs)                         │ ┃
┃  │   • BusinessContext (industry, goals, grains)             │ ┃
┃  │   • TableClassifications (heuristic roles)                │ ┃
┃  │                                                            │ ┃
┃  │ LLM Prompt:                                                │ ┃
┃  │   "Generate DETAILED plan with EXACT specifications:      │ ┃
┃  │    - Bronze: list all source tables                       │ ┃
┃  │    - Silver dimensions: name, SCD type, grain, columns    │ ┃
┃  │    - Silver facts: name, grain, date col, FKs, measures   │ ┃
┃  │    - Gold: name, source, grain, metrics with agg types"   │ ┃
┃  │                                                            │ ┃
┃  │ Output: Detailed JSON plan                                │ ┃
┃  │   {                                                        │ ┃
┃  │     "bronze": ["customers", "orders", ...],               │ ┃
┃  │     "silver": {                                            │ ┃
┃  │       "dimensions": [{                                     │ ┃
┃  │         "name": "dim_customers",                           │ ┃
┃  │         "scd_type": 2,                                     │ ┃
┃  │         "grain": "one row per customer",                   │ ┃
┃  │         "columns": [...]                                   │ ┃
┃  │       }],                                                  │ ┃
┃  │       "facts": [{...}]                                     │ ┃
┃  │     },                                                     │ ┃
┃  │     "gold": [{...}]                                        │ ┃
┃  │   }                                                        │ ┃
┃  └───────────────────────────────────────────────────────────┘ ┃
┃                              │                                  ┃
┃                              ▼                                  ┃
┃  ┌───────────────────────────────────────────────────────────┐ ┃
┃  │ 4b. DISPLAY CONCRETE PLAN                                 │ ┃
┃  │ ─────────────────────────                                 │ ┃
┃  │ Function: display_concrete_plan()                         │ ┃
┃  │                                                            │ ┃
┃  │ Shows:                                                     │ ┃
┃  │   📦 BRONZE LAYER                                         │ ┃
┃  │      • bronze_customers                                    │ ┃
┃  │      • bronze_orders                                       │ ┃
┃  │      ...                                                   │ ┃
┃  │                                                            │ ┃
┃  │   🔷 SILVER - DIMENSIONS                                  │ ┃
┃  │      dim_customers (SCD Type 2)                           │ ┃
┃  │        Source: customers                                   │ ┃
┃  │        Grain: one row per customer per valid period       │ ┃
┃  │        Columns: customer_id, name, email, ...             │ ┃
┃  │                                                            │ ┃
┃  │   📊 SILVER - FACTS                                       │ ┃
┃  │      fct_orders                                           │ ┃
┃  │        Source: orders                                      │ ┃
┃  │        Grain: one row per order                           │ ┃
┃  │        Date: order_date                                    │ ┃
┃  │        FKs: customer_id → dim_customers                   │ ┃
┃  │        Measures: total_amount, discount, tax              │ ┃
┃  │                                                            │ ┃
┃  │   🥇 GOLD - AGGREGATES                                    │ ┃
┃  │      gold_daily_revenue                                   │ ┃
┃  │        Metrics: total_revenue = SUM(total_amount)         │ ┃
┃  │                 order_count = COUNT(*)                     │ ┃
┃  └───────────────────────────────────────────────────────────┘ ┃
┃                              │                                  ┃
┃                              ▼                                  ┃
┃  ┌───────────────────────────────────────────────────────────┐ ┃
┃  │ 4c. GET USER FEEDBACK                                     │ ┃
┃  │ ─────────────────────                                     │ ┃
┃  │ User types natural language:                              │ ┃
┃  │   • "make revenue weekly instead of daily"                │ ┃
┃  │   • "split customers into B2B and B2C"                    │ ┃
┃  │   • "add customer lifetime value"                         │ ┃
┃  │   • "approve" (accept plan)                               │ ┃
┃  │   • "reject" (abort)                                      │ ┃
┃  └───────────────────────────────────────────────────────────┘ ┃
┃                              │                                  ┃
┃                  ┌───────────┴───────────┐                     ┃
┃                  │                       │                     ┃
┃             "approve"                "feedback"                ┃
┃                  │                       │                     ┃
┃                  │                       ▼                     ┃
┃                  │  ┌───────────────────────────────────────┐ ┃
┃                  │  │ 4d. LLM REFINE PLAN                   │ ┃
┃                  │  │ ───────────────────                   │ ┃
┃                  │  │ Function: llm_refine_plan()           │ ┃
┃                  │  │                                        │ ┃
┃                  │  │ Input:                                 │ ┃
┃                  │  │   • Current plan (JSON)                │ ┃
┃                  │  │   • User feedback (string)             │ ┃
┃                  │  │   • Schema (for validation)            │ ┃
┃                  │  │   • Context (business rules)           │ ┃
┃                  │  │                                        │ ┃
┃                  │  │ LLM Prompt:                            │ ┃
┃                  │  │   "Interpret feedback: 'make weekly'  │ ┃
┃                  │  │    Current plan has daily grain       │ ┃
┃                  │  │    Change gold_daily_X to weekly      │ ┃
┃                  │  │    Validate: makes sense ✓            │ ┃
┃                  │  │    Return COMPLETE amended plan"       │ ┃
┃                  │  │                                        │ ┃
┃                  │  │ Output: Refined JSON plan              │ ┃
┃                  │  └───────────────────────────────────────┘ ┃
┃                  │                       │                     ┃
┃                  │                       ▼                     ┃
┃                  │  ┌───────────────────────────────────────┐ ┃
┃                  │  │ 4e. SHOW DIFF                         │ ┃
┃                  │  │ ─────────────                         │ ┃
┃                  │  │ Function: show_diff()                 │ ┃
┃                  │  │                                        │ ┃
┃                  │  │ CHANGES:                               │ ┃
┃                  │  │   ✓ Added: gold_weekly_revenue        │ ┃
┃                  │  │   ✗ Removed: gold_daily_revenue       │ ┃
┃                  │  │   ⟳ Modified: fct_orders (added tax)  │ ┃
┃                  │  └───────────────────────────────────────┘ ┃
┃                  │                       │                     ┃
┃                  │                       │                     ┃
┃                  │                       └──────┐              ┃
┃                  │                              │              ┃
┃                  │         ┌────────────────────┘              ┃
┃                  │         │ LOOP BACK TO 4b                   ┃
┃                  │         │ (unlimited iterations)            ┃
┃                  │         └─────────────────┐                 ┃
┃                  │                           │                 ┃
┃                  ▼                           │                 ┃
┃  ┌───────────────────────────────────────────┼───────────────┐┃
┃  │ 4f. CONVERT TO MODELING PLAN              │               │┃
┃  │ ────────────────────────────              │               │┃
┃  │ Function: convert_plan_dict_to_modeling_plan()            │┃
┃  │                                           │               │┃
┃  │ Converts LLM JSON → Pydantic ModelingPlan │               │┃
┃  │   • DimensionPlan objects                 │               │┃
┃  │   • FactPlan objects                      │               │┃
┃  │   • GoldPlan objects                      │               │┃
┃  │   • MetricDefinition objects              │               │┃
┃  └───────────────────────────────────────────┼───────────────┘┃
┗━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━┷━━━━━━━━━━━━━━━━┛
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 5: GENERATE DBT PROJECT                                   │
│  ─────────────────────────                                      │
│  • Generate SQL from templates                                  │
│  • Create Bronze/Silver/Gold models                             │
│  • Generate schema.yml files                                    │
│  • Create semantic_layer.yml                                    │
│  • Write README.md                                              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                         ✅ SUCCESS!
```

## Data Flow

```
PostgreSQL DB
     │
     │ (SQLAlchemy)
     ▼
Schema Object
     │
     │ (User interaction)
     ▼
BusinessContext
     │
     │ (FK graph analysis)
     ▼
TableClassifications ─────────┐
     │                        │
     │                        │ (Heuristics)
     ▼                        │
┌─────────────────────────────┴───────────────────────────┐
│ LLM (Ollama)                                            │
│   Model: qwen-data or qwen2.5-coder                     │
│                                                         │
│   Input: Schema + Context + Classifications             │
│   Output: Detailed JSON plan                            │
│                                                         │
│   ┌─────────────────────────────────────────────────┐  │
│   │ Generate Initial Plan                           │  │
│   │   ↓                                             │  │
│   │ Interpret User Feedback  ←──────┐              │  │
│   │   ↓                             │              │  │
│   │ Validate Changes                │              │  │
│   │   ↓                             │              │  │
│   │ Refine Plan                     │              │  │
│   │   ↓                             │              │  │
│   │ More feedback needed? ─YES──────┘              │  │
│   │   │                                             │  │
│   │  NO                                             │  │
│   └───┼─────────────────────────────────────────────┘  │
│       │                                                 │
└───────┼─────────────────────────────────────────────────┘
        │
        ▼
Detailed Plan JSON
        │
        │ (convert_plan_dict_to_modeling_plan)
        ▼
ModelingPlan (Pydantic)
        │
        │ (Jinja2 templates)
        ▼
dbt Project Files
        │
        ▼
    User's disk
```

## Component Relationships

```
┌──────────────────────────────────────────────────────────────┐
│ schemalytics/cli.py                                          │
│                                                              │
│  @click.command()                                            │
│  def generate():                                             │
│    schema = extract_schema() ─────────┐                     │
│    context = gather_context()         │                     │
│    classifications = classify_fks()   │                     │
│    plan = interactive_refinement() ───┼─────────────┐       │
│    generate_dbt_project(plan) ────────┼─────────┐   │       │
└───────────────────────────────────────┼─────────┼───┼───────┘
                                        │         │   │
                ┌───────────────────────┘         │   │
                │                                 │   │
┌───────────────▼─────────────────────────────────┼───┼───────┐
│ schemalytics/planner.py                         │   │       │
│                                                 │   │       │
│  def interactive_refinement_loop():             │   │       │
│    plan = llm_generate_detailed_plan() ─────┐  │   │       │
│    while True:                              │  │   │       │
│      display_concrete_plan(plan)            │  │   │       │
│      feedback = input()                     │  │   │       │
│      if approved: return convert(plan) ─────┼──┼───┼───┐   │
│      plan = llm_refine_plan() ──────────────┼──┘   │   │   │
│      show_diff(old, plan)                   │      │   │   │
│                                             │      │   │   │
│  def llm_generate_detailed_plan(): ─────────┘      │   │   │
│    return llm.query_json(prompt)                   │   │   │
│                                                    │   │   │
│  def llm_refine_plan(): ───────────────────────────┘   │   │
│    return llm.query_json(prompt)                       │   │
└────────────────────────────────────────────────────────┼───┘
                                                         │
                ┌────────────────────────────────────────┘
                │
┌───────────────▼──────────────────────────────────────────────┐
│ schemalytics/generators/dbt.py                               │
│                                                              │
│  def generate_dbt_project(plan):                             │
│    for dim in plan.dimensions:                               │
│      generate_dimension_sql(dim)                             │
│    for fact in plan.facts:                                   │
│      generate_fact_sql(fact)                                 │
│    for gold in plan.gold:                                    │
│      generate_gold_sql(gold)                                 │
│    generate_semantic_layer(plan)                             │
└──────────────────────────────────────────────────────────────┘
```

## State Machine

```
        START
          │
          ▼
    Extract Schema
          │
          ▼
   Gather Context
          │
          ▼
Classify Tables (Heuristics)
          │
          ▼
    ┌─────────────┐
    │  ITERATION  │◄────────────────────┐
    │   COUNTER   │                     │
    └─────┬───────┘                     │
          │                             │
          ▼                             │
┌──────────────────┐                    │
│  Generate Plan   │                    │
│   (LLM Call)     │                    │
└──────┬───────────┘                    │
       │                                │
       ▼                                │
┌──────────────────┐                    │
│  Display Plan    │                    │
│  (Concrete view) │                    │
└──────┬───────────┘                    │
       │                                │
       ▼                                │
┌──────────────────┐                    │
│  Wait for Input  │                    │
└──────┬───────────┘                    │
       │                                │
       ├──"approve"──►┌─────────────┐  │
       │              │  APPROVED   │  │
       │              └──────┬──────┘  │
       │                     │         │
       ├──"reject"───►┌──────▼──────┐ │
       │              │  REJECTED   │ │
       │              └─────────────┘ │
       │                              │
       └──feedback───►┌─────────────┐ │
                      │ Refine Plan │ │
                      │ (LLM Call)  │ │
                      └──────┬──────┘ │
                             │        │
                             ▼        │
                      ┌─────────────┐ │
                      │  Show Diff  │ │
                      └──────┬──────┘ │
                             │        │
                             └────────┘
                             
    APPROVED
       │
       ▼
Convert to ModelingPlan
       │
       ▼
Generate dbt Project
       │
       ▼
     SUCCESS
```

## Key Innovations

### 1. Two-Phase LLM Usage
```
Phase 1: GENERATE
├─ Input: Full schema + business context
├─ Output: Complete detailed plan
└─ Purpose: Create initial comprehensive proposal

Phase 2: REFINE  
├─ Input: Current plan + user feedback
├─ Output: Amended complete plan
└─ Purpose: Iterative improvement
```

### 2. Diff-Based Feedback
```
Old Plan → New Plan → Diff Calculation → Display Changes
  │          │             │                    │
  │          │             │                    ▼
  │          │             │              User sees:
  │          │             │              ✓ Added
  │          │             │              ✗ Removed  
  │          │             │              ⟳ Modified
  │          │             │
  │          │             └─ Helps user track changes
  └──────────┴────────────── Maintains history
```

### 3. Stateless Refinement
```
Each refinement call is independent:
  
  llm_refine_plan(current_plan, "make weekly")
      │
      ├─ Doesn't maintain conversation history
      ├─ Always passes full current plan
      └─ Returns complete new plan (not delta)

Advantages:
  ✓ No context drift over iterations
  ✓ Each step is reproducible
  ✓ Can parallelize in future
```