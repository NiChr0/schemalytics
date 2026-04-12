# Schemalytics — Architecture

## System Overview

```
User runs: schemalytics generate -c postgresql://... -o ./dbt_project
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 1: EXTRACT SCHEMA                                         │
│  extractors/postgres.py                                         │
│  • SQLAlchemy connects to PostgreSQL                            │
│  • Extracts tables, columns, PKs, FKs                           │
│  • Returns Schema (Pydantic)                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 2: AGENT PIPELINE  planner.py / run_pipeline()            │
│                                                                 │
│  Agent 1 — infer_industry()                                     │
│    Input:  Schema (table names, column names, FKs)              │
│    Output: IndustryInference (industry, business_type,          │
│            confidence, reasoning, needs_clarification)          │
│    confidence < 3 → ask user to confirm or describe business    │
│                                                                 │
│  Agent 2 — suggest_metrics()                                    │
│    Input:  Schema + IndustryInference                           │
│    Output: MetricsSuggestion (metrics, goals, grain,            │
│            confidence, clarification_question)                  │
│    confidence < 3 → ask user to confirm / add / remove          │
│                                                                 │
│  FK Graph Heuristics — classify_by_fk_graph()                   │
│    (runs before Agent 3 as a prior, not ground truth)           │
│    2+ outgoing FKs, 0 incoming → fact                           │
│    2+ incoming FKs, 0 outgoing → dimension                      │
│                                                                 │
│  Agent 3 — classify_tables()                                    │
│    Input:  Schema + PipelineContext (partial) + heuristics      │
│    Output: list[TableClassificationResult] (role, confidence)   │
│    confidence < 3 tables → flagged for user review              │
│                                                                 │
│  ── SUMMARY GATE (always runs) ──────────────────────────────── │
│    Prints consolidated context: industry, metrics, goals,       │
│    grain, table roles. User can correct or press Enter.         │
│    Corrections → re-run Agents 1-3 with feedback                │
│                                                                 │
│  Agent 4 — generate_modeling_plan()                             │
│    Input:  Schema + PipelineContext (full)                      │
│    Call A: Silver (bronze + dimensions + facts)                 │
│    Sanitize: _sanitize_plan() — validates columns, enforces     │
│              numeric-only measures, validates derived exprs     │
│    Call B: Gold — receives only sanitized Silver as context     │
│    Output: ModelingPlan (bronze, dimensions, facts, gold)       │
│    Always surfaces plan to user for review                      │
│                                                                 │
│  Agent 5 — refine_modeling_plan() [loop]                        │
│    Input:  ModelingPlan + user feedback                         │
│    Output: Revised ModelingPlan                                 │
│    Prints diff after each iteration. Loops until approved.      │
│    Press Enter → approve; type "cancel" → abort                 │
│                                                                 │
│  Returns: (ModelingPlan, PipelineContext) or None               │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  STEP 3: GENERATE DBT PROJECT  generators/dbt.py                │
│  • Bronze SQL:  stg_<schema>_<table>.sql  (materialized view)   │
│  • Silver SQL:  dim_*.sql, fct_*.sql      (materialized table)  │
│  • Gold SQL:    agg_<grain>_<metric>.sql  (materialized table)  │
│  • schema.yml files, dbt_project.yml, sources.yml               │
│  • semantic_layer.yml for LLM-powered analytics                 │
│  • README.md                                                    │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                        dbt project on disk
```

## Confidence Rule (all agents)

```
confidence == 3  →  print notification, proceed automatically
confidence == 2  →  ask user to confirm or correct
confidence == 1  →  ask user, explain why agent is uncertain
```

User input is always free-text. Corrections are passed back through the same agent with updated context.

## LLM Provider Abstraction

All agent calls go through `llm.query_structured()`:

```
SCHEMALYTICS_LLM_PROVIDER=ollama (default)
  └── instructor.from_openai(OpenAI(base_url="http://localhost:11434/v1"))
      model: gemma3:4b  (Ollama OpenAI-compatible endpoint)
      num_ctx: 12288 (fixed across all calls — changing triggers model reload)

  Override the default model for all agents:
      SCHEMALYTICS_OLLAMA_MODEL=<model-name>

  Fine-tuned models available on Ollama Hub (Qwen3.5-4B QLoRA):
      nichr0/schemalytics-classification-agent  — Agent 3 (fact/dim/bridge/reference)
      nichr0/schemalytics-silver-agent          — Agent 4a (Silver plan generation)
      nichr0/schemalytics-gold-agent            — Agent 4b (Gold plan generation)
  Per-agent override env vars: SCHEMALYTICS_AGENT3_MODEL, SCHEMALYTICS_AGENT4A_MODEL, SCHEMALYTICS_AGENT4B_MODEL

SCHEMALYTICS_LLM_PROVIDER=anthropic
  └── instructor.from_anthropic(Anthropic(api_key=...))
      model: claude-sonnet-4-20250514
```

`instructor` wraps the client and enforces that every response matches the target Pydantic model. Max retries: 3. No `json.loads()` anywhere in the pipeline.

## Data Flow

```
Schema
  │
  ├─ Agent 1 ──────────────────────► IndustryInference
  │                                         │
  ├─ Agent 2 (schema + industry) ──────► MetricsSuggestion
  │                                         │
  ├─ classify_by_fk_graph() ──► heuristics  │
  │                                  │      │
  ├─ Agent 3 (schema + partial ctx) ◄┤      │
  │                 │                       │
  │         [TableClassificationResult]     │
  │                 │                       │
  └─ PipelineContext ◄──────────────────────┘
            │
     [Summary Gate]
            │
       Agent 4 ──────────────────────► ModelingPlan
                                            │
                               [Refinement loop — Agent 5]
                                            │
                             generate_dbt_project(schema, plan, ctx)
                                            │
                                    dbt project on disk
```

## Key Design Decisions

- **Template-based SQL** — Jinja2 fills templates; LLM never writes raw SQL. Do not change this.
- **instructor for structured output** — Every agent call returns a validated Pydantic model. No JSON parsing, no fallbacks.
- **FK heuristics as prior** — `classify_by_fk_graph()` results feed Agent 3 as a starting point; the agent validates and adjusts.
- **Pipeline contract** — Silver is sanitized (`_sanitize_plan()`) before Gold sees it. Gold only references schema-validated measures and declared derived measure aliases. Gold expressions are rejected — computed values must be declared as `DerivedMeasure` objects in Silver.
- **Type-aware measure detection** — `_col_is_measure()` enforces numeric-only measures: float/money always qualify; integers qualify only when the column name contains a measure keyword (qty, amount, price, etc.).
- **Stateless refinement** — Each Agent 5 call receives the full current `ModelingPlan` + feedback. No conversation history maintained.
- **Provider-agnostic pipeline** — Only `llm.py` knows which provider is active. The rest of the pipeline sees only `query_structured()`.
- **No dbt execution** — Schemalytics generates code files only. Users run `dbt run` themselves.
