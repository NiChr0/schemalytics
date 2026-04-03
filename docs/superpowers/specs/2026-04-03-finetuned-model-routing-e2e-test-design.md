# Design: Fine-Tuned Model Routing + End-to-End Test

**Date:** 2026-04-03
**Branch:** `finetune_semantic`

---

## Problem

Three fine-tuned models exist for Agents 3, 4a, 4b but are never used. All seven agent calls in `planner.py` pass `model=None`, which falls through to the hardcoded `gemma3-12b` default in `llm.py`. `SCHEMALYTICS_OLLAMA_MODEL` is documented everywhere but never read by the code. The integration test is outdated: it calls agents individually, skips Agents 5 and 6, and checks for `semantic_layer.yml` (removed) instead of `semantic_models.yml`.

---

## Design

### 1 — Per-agent model routing

**`schemalytics/llm.py`**

Replace hardcoded default with env var read:
```python
OLLAMA_DEFAULT_MODEL = os.environ.get("SCHEMALYTICS_OLLAMA_MODEL", "gemma3-12b")
```
This makes `SCHEMALYTICS_OLLAMA_MODEL` functional for Agents 1, 2, 5, 6 (general-purpose agents).

**`schemalytics/planner.py`**

Add three constants near each agent's system prompt, with env var overrides:
```python
_AGENT3_MODEL  = os.environ.get("SCHEMALYTICS_AGENT3_MODEL",  "nichr0/schemalytics-classification-agent")
_AGENT4A_MODEL = os.environ.get("SCHEMALYTICS_AGENT4A_MODEL", "nichr0/schemalytics-silver-agent")
_AGENT4B_MODEL = os.environ.get("SCHEMALYTICS_AGENT4B_MODEL", "nichr0/schemalytics-gold-agent")
```

Pass each to the corresponding `llm.query_structured()` call:
- `classify_tables()` → `model=_AGENT3_MODEL`
- `generate_modeling_plan()` silver call → `model=_AGENT4A_MODEL`
- `generate_modeling_plan()` gold call → `model=_AGENT4B_MODEL`
- Agents 1, 2, 5, 6 → `model=None` (use `OLLAMA_DEFAULT_MODEL`)

**Model routing table:**

| Agent | Default model | Override env var |
|---|---|---|
| 1 — industry inference | `gemma3-12b` | `SCHEMALYTICS_OLLAMA_MODEL` |
| 2 — metrics suggestion | `gemma3-12b` | `SCHEMALYTICS_OLLAMA_MODEL` |
| 3 — table classification | `nichr0/schemalytics-classification-agent` | `SCHEMALYTICS_AGENT3_MODEL` |
| 4a — silver plan | `nichr0/schemalytics-silver-agent` | `SCHEMALYTICS_AGENT4A_MODEL` |
| 4b — gold plan | `nichr0/schemalytics-gold-agent` | `SCHEMALYTICS_AGENT4B_MODEL` |
| 5 — plan refinement | `gemma3-12b` | `SCHEMALYTICS_OLLAMA_MODEL` |
| 6 — semantic layer | `gemma3-12b` | `SCHEMALYTICS_OLLAMA_MODEL` |

---

### 2 — Startup model availability check

New function `_check_finetuned_models()` in `planner.py`, called once at the top of `run_pipeline()`. Skipped entirely when `SCHEMALYTICS_LLM_PROVIDER=anthropic`.

**Logic:**
1. Run `ollama list` via `subprocess.run`, parse model names from stdout
2. For each of `_AGENT3_MODEL`, `_AGENT4A_MODEL`, `_AGENT4B_MODEL`: check if it appears in the list. Skip the check if the constant was overridden via env var to a non-fine-tuned model (i.e. only check names starting with `nichr0/`)
3. For each missing model: print a warning with the pull command and note that `OLLAMA_DEFAULT_MODEL` will be used instead
4. If any are missing, prompt `Continue anyway? [y/N]`
   - `n` (default) → `SystemExit(1)`
   - `y` → for each missing model, patch its module-level constant to `OLLAMA_DEFAULT_MODEL`
5. If `ollama list` itself fails (Ollama not running), surface the error clearly and exit

**Example output:**
```
Warning: fine-tuned model 'nichr0/schemalytics-classification-agent' is not pulled.
  → Run: ollama pull nichr0/schemalytics-classification-agent
  → Agent 3 will use gemma3-12b instead (quality may be lower).

Continue anyway? [y/N]
```

---

### 3 — Integration test overhaul

**`tests/test_integration.py`** — full rewrite with two tests:

**`test_per_agent_models_configured`**
- No Ollama required (not skipped by `SCHEMALYTICS_INTEGRATION` guard)
- Imports `_AGENT3_MODEL`, `_AGENT4A_MODEL`, `_AGENT4B_MODEL` from `schemalytics.planner`
- Asserts each equals the expected fine-tuned model name
- Catches accidental regressions if the constants are removed or renamed

**`test_full_pipeline_northwind`** (requires `SCHEMALYTICS_INTEGRATION=1`)
- Calls `run_pipeline()` with:
  - `monkeypatch.setattr("schemalytics.planner._check_finetuned_models", lambda: None)` — bypasses `ollama list` so CI doesn't need it
  - `monkeypatch.setattr("builtins.input", lambda _: "")` — auto-approves the refinement loop
- Verifies return is a 3-tuple `(plan, ctx, semantic_layer)`
- Calls `generate_dbt_project(schema, plan, tmpdir, "northwind_test", context=ctx, semantic_layer=semantic_layer)`
- Asserts:
  - `dbt_project.yml` exists
  - `models/bronze/`, `models/silver/dimensions/`, `models/silver/facts/`, `models/gold/` exist
  - `semantic_models.yml` exists
  - bronze SQL file count == `len(plan.bronze)`
  - `semantic_layer.semantic_models` is non-empty
  - `len(semantic_layer.metrics) >= 0` (zero is allowed for sparse schemas)

---

## Files Changed

| File | Change |
|---|---|
| `schemalytics/llm.py` | 1 line: read `SCHEMALYTICS_OLLAMA_MODEL` env var |
| `schemalytics/planner.py` | Add 3 model constants, pass to 3 `llm.query_structured` calls, add `_check_finetuned_models()`, call it at top of `run_pipeline()` |
| `tests/test_integration.py` | Full rewrite |

---

## Out of Scope

- Per-agent `num_ctx` tuning for the fine-tuned models (they were trained at 12288, same as current setting — no change needed)
- Agent 6 fine-tuning (not trained yet; uses `gemma3-12b`)
- CI automation (integration test still requires manual `SCHEMALYTICS_INTEGRATION=1`)
