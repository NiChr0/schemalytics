# Schemalytics - Project Memory

## What It Is
PostgreSQL → LLM-ready semantic layer tool. Analyzes DB schema, generates dimensional models (medallion: Bronze→Silver→Gold), and creates complete dbt projects with metadata for self-service analytics. Supports Ollama (default) and Anthropic LLMs via `instructor`.

**Version**: 0.1.3 | **License**: Apache 2.0 | **Python**: ≥3.10

## Key Files
- [pyproject.toml](pyproject.toml) — build config, deps, CLI entry points
- [schemalytics/__init__.py](schemalytics/__init__.py) — public exports
- [schemalytics/cli.py](schemalytics/cli.py) — Click CLI: `generate`, `extract` commands (no --context flag)
- [schemalytics/models.py](schemalytics/models.py) — Pydantic models incl. new agent models (IndustryInference, MetricsSuggestion, TableClassificationResult, PipelineContext)
- [schemalytics/llm.py](schemalytics/llm.py) — instructor-based abstraction: Ollama or Anthropic via SCHEMALYTICS_LLM_PROVIDER env var
- [schemalytics/planner.py](schemalytics/planner.py) — Five-agent pipeline + FK graph heuristics (run_pipeline() orchestrator)
- [schemalytics/templates.py](schemalytics/templates.py) — Jinja2 dbt SQL templates
- [schemalytics/extractors/postgres.py](schemalytics/extractors/postgres.py) — SQLAlchemy schema extraction
- [schemalytics/generators/dbt.py](schemalytics/generators/dbt.py) — dbt project generation
- [tests/test_agents.py](tests/test_agents.py) — 13 unit tests (all passing), mocked LLM
- [tests/test_integration.py](tests/test_integration.py) — e2e test (SCHEMALYTICS_INTEGRATION=1 to run)

## Architecture (Post-Rebuild)
```
PostgreSQL → extract_schema() → run_pipeline() [5 agents] → generate_dbt_project()

Agent 1: infer_industry()       → IndustryInference
Agent 2: suggest_metrics()      → MetricsSuggestion
Agent 3: classify_tables()      → list[TableClassificationResult] (uses FK heuristics as prior)
         [Summary gate - mandatory user review]
Agent 4: generate_modeling_plan() → ModelingPlan
Agent 5: refine_modeling_plan()   → ModelingPlan (refinement loop)
```

**Layers**: Bronze (raw views) → Silver (star schema: dim_*, fct_*) → Gold (agg_*_* metrics)

## Dependencies
- `click>=8.0`, `pydantic>=2.0`, `sqlalchemy>=2.0`, `psycopg2-binary>=2.9`
- `httpx>=0.24`, `jinja2>=3.0`, `pyyaml>=6.0`
- `instructor[anthropic]>=1.0.0`, `ollama>=0.3.0` (new — agent LLM calls)
- Dev: `pytest>=7.0`, `pytest-cov>=4.0`, `ruff>=0.1`

## LLM Provider Config
- Default: Ollama at localhost:11434, model `qwen3-30b-data` (MoE, 3.3B activated, 256K native ctx)
- Anthropic: `SCHEMALYTICS_LLM_PROVIDER=anthropic` + `ANTHROPIC_API_KEY`, model `claude-sonnet-4-20250514`
- Entry point: `llm.query_structured(system, user, response_model)` — returns typed Pydantic model

## Confidence Rule (all agents)
- confidence 3 → auto-proceed, print notification
- confidence 2 → ask user to confirm or correct
- confidence 1 → ask user, explain uncertainty
- User input always free-text; corrections passed back through the same agent

## CLI
```bash
schemalytics generate -c postgresql://... -o ./dbt_project -n my_project
schemalytics extract -c postgresql://... -o schema.json
```
No `--context` flag. No `context.yaml`. No `plan` command.

## Deleted
- `industry_taxonomy.py` — gone
- `context.yaml` support — gone from cli.py and planner.py
- Raw `json.loads()` / `json.JSONDecodeError` fallbacks — gone (instructor handles this)

## Testing
- Unit tests: `pytest tests/test_agents.py -v` (13 tests, no LLM needed, all pass)
- Integration: `SCHEMALYTICS_INTEGRATION=1 pytest tests/test_integration.py -v` (needs Ollama + Northwind)
- Test DB: `docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres ghcr.io/nichr0/northwind-postgres:latest`

## Agent Instruction Files (root level)
- [AGENTS.md](AGENTS.md) — main project context, LLM-agnostic, committed to repo (always read first)
- [CLAUDE.md](CLAUDE.md) — Claude Code-specific thin wrapper, gitignored (references AGENTS.md)
- [dev.md](dev.md) — feature development workflow
- [testing.md](testing.md) — testing & validation (3 levels: unit, integration, e2e)
- [release.md](release.md) — PyPI release workflow

## Design Patterns
- FK graph heuristics: 2+ outgoing FKs → fact; 2+ incoming FKs → dimension (now feeds Agent 3 as prior)
- instructor enforces Pydantic model output from LLM — no JSON parsing fallbacks anywhere
- Agent 3 wraps list[TableClassificationResult] in a container model (_ClassificationList) because instructor can't return list[T] directly
- _PipelineContextAdapter in cli.py provides .goals for generator backward compat (generator expects BusinessContext)
- ruff excludes schemalytics/bin/ (Haxe-generated daff.py)

## _sanitize_plan() — Structural Invariants (planner.py)
Post-LLM gate that enforces universal correctness regardless of dataset. Key helpers:

```python
_FLOAT_TYPES / _INT_TYPES / _MEASURE_KEYWORDS  # type+name heuristic constants
def _col_is_measure(col) -> bool          # floats always; ints only if name has measure keyword
def _is_sql_expression(s) -> bool         # checks for operator chars
def _extract_expression_col_refs(expr)    # regex-extracts column tokens from SQL expressions
_AUDIT_TIMESTAMP_NAMES                    # set of audit-only timestamp names excluded from tx-date detection
def _has_transaction_date(table) -> bool  # type-first detection; excludes audit timestamps
```

Fact sanitization order per fact:
1. Date column: detect by data type, exclude audit timestamps
2. dimension_keys: non-FK numeric cols reclassified to measures via _col_is_measure
3. measures: validate; preserve SQL expressions; prune non-existent simple col refs
4. auto-fill measures: _col_is_measure (not type-alone)
5. is_factless: auto-set when no numeric columns found

After facts loop → build `fact_model_cols` (dim_keys ∪ measures ∪ date_column per fact).

Gold validation uses `fact_model_cols` (not raw source table cols). Expression metrics validated via `_extract_expression_col_refs`. Models named `*_ytd` with daily/weekly grain → grain forced to "yearly".

## dbt Generator — Key Behaviors (generators/dbt.py)
- Surrogate key for periodic snapshots: appends date_column when it's in dimension_keys but not in natural PK
- SELECT dedup: normalises "table.col as alias" → alias for dedup key
- packages.yml: pinned to `"1.3.0"` (not floating range)
- macros/incremental_date_filter.sql: shared macro — no copy-pasted WHERE blocks in facts
- macros/generate_schema_name.sql: routes bronze/silver/gold to separate warehouse schemas
- sources.yml: per-source freshness block emitted when an updated_at column exists
- nullable_cols dict (built from source schema) passed to SILVER_FACTS_SCHEMA_TEMPLATE — gates not_null tests on actual column nullability

## templates.py — SILVER_FACTS_SCHEMA_TEMPLATE Guards
- `grain: {{ fact.grain }}` (not hardcoded "transaction")
- dimension_keys loop: skips date_column; conditionally adds not_null + relationships based on nullable_cols
- date_column: not_null only if not in nullable_cols
- measures loop: skips date_column, SQL expressions (* / spaces), and columns already in dimension_keys
