# Fine-Tuned Model Routing + E2E Test Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route Agents 3, 4a, 4b to their fine-tuned Ollama models by default, warn the user if models aren't pulled, and update the integration test to cover the full 6-agent pipeline including Agent 6 (semantic layer).

**Architecture:** Three module-level constants in `planner.py` (env-var overridable) are passed as `model=` to the three fine-tuned agent calls. A `_check_finetuned_models()` guard runs once at pipeline start, shells out to `ollama list`, warns on missing models, and prompts to continue or abort. `llm.py` gets one line changed to honour `SCHEMALYTICS_OLLAMA_MODEL`. The integration test is rewritten to use `run_pipeline()` end-to-end.

**Tech Stack:** Python 3.10+, pytest, subprocess (stdlib), existing `instructor`/`openai` Ollama client.

---

## File Map

| File | Change |
|---|---|
| `schemalytics/llm.py` | 1 line: read `SCHEMALYTICS_OLLAMA_MODEL` env var |
| `schemalytics/planner.py` | Add `import subprocess`; add 3 model constants; pass `model=` to 3 agent calls; add `_check_finetuned_models()`; call it at top of `run_pipeline()` |
| `tests/test_agents.py` | Append 3 unit tests for `_check_finetuned_models` |
| `tests/test_integration.py` | Full rewrite: 2 tests |

---

## Task 1: `llm.py` — honour `SCHEMALYTICS_OLLAMA_MODEL`

**Files:**
- Modify: `schemalytics/llm.py:11`

- [ ] **Step 1: Make the change**

Open [`schemalytics/llm.py`](schemalytics/llm.py). Line 11 currently reads:
```python
OLLAMA_DEFAULT_MODEL = "gemma3-12b"
```
Replace with:
```python
OLLAMA_DEFAULT_MODEL = os.environ.get("SCHEMALYTICS_OLLAMA_MODEL", "gemma3-12b")
```
`os` is already imported at line 4.

- [ ] **Step 2: Verify no tests break**

```bash
pytest tests/test_agents.py -v
```
Expected: all 13 tests pass (none of them set `SCHEMALYTICS_OLLAMA_MODEL`).

- [ ] **Step 3: Commit**

```bash
git add schemalytics/llm.py
git commit -m "feat: read SCHEMALYTICS_OLLAMA_MODEL env var in llm.py"
```

---

## Task 2: Per-agent model constants + wire into agent calls

**Files:**
- Modify: `schemalytics/planner.py` (near `_AGENT3_SYSTEM`, lines 427–432, 887–892, 932–937)
- Test: `tests/test_integration.py` (the `test_per_agent_models_configured` test — written first)

- [ ] **Step 1: Write the failing test**

Open [`tests/test_integration.py`](tests/test_integration.py). Replace its entire contents with:

```python
"""Integration and model-config tests for the Schemalytics pipeline.

test_per_agent_models_configured: no Ollama or DB required, always runs.
test_full_pipeline_northwind: requires SCHEMALYTICS_INTEGRATION=1, Ollama, and Northwind.
"""
from __future__ import annotations

import os
import tempfile

import pytest

NORTHWIND_DSN = os.environ.get(
    "NORTHWIND_DSN", "postgresql://postgres:postgres@localhost:5432/northwind"
)

integration_only = pytest.mark.skipif(
    os.environ.get("SCHEMALYTICS_INTEGRATION") != "1",
    reason="Set SCHEMALYTICS_INTEGRATION=1 to run integration tests",
)


def test_per_agent_models_configured() -> None:
    """Fine-tuned model constants must resolve to Ollama Hub names when no env override is set."""
    from schemalytics.planner import _AGENT3_MODEL, _AGENT4A_MODEL, _AGENT4B_MODEL

    assert _AGENT3_MODEL == "nichr0/schemalytics-classification-agent", (
        f"Expected nichr0/schemalytics-classification-agent, got {_AGENT3_MODEL!r}"
    )
    assert _AGENT4A_MODEL == "nichr0/schemalytics-silver-agent", (
        f"Expected nichr0/schemalytics-silver-agent, got {_AGENT4A_MODEL!r}"
    )
    assert _AGENT4B_MODEL == "nichr0/schemalytics-gold-agent", (
        f"Expected nichr0/schemalytics-gold-agent, got {_AGENT4B_MODEL!r}"
    )


@integration_only
def test_full_pipeline_northwind(monkeypatch: pytest.MonkeyPatch) -> None:
    pass  # implemented in Task 4
```

- [ ] **Step 2: Run test to verify it fails**

```bash
pytest tests/test_integration.py::test_per_agent_models_configured -v
```
Expected: FAIL with `ImportError: cannot import name '_AGENT3_MODEL' from 'schemalytics.planner'`

- [ ] **Step 3: Add model constants to `planner.py`**

Open [`schemalytics/planner.py`](schemalytics/planner.py). After the imports block (after line 22, before `def _ts()`), add:

```python
# ── Per-agent model selection ──────────────────────────────────────────────────
# Fine-tuned models are the defaults. Override via env var for ablation testing.
_AGENT3_MODEL  = os.environ.get("SCHEMALYTICS_AGENT3_MODEL",  "nichr0/schemalytics-classification-agent")
_AGENT4A_MODEL = os.environ.get("SCHEMALYTICS_AGENT4A_MODEL", "nichr0/schemalytics-silver-agent")
_AGENT4B_MODEL = os.environ.get("SCHEMALYTICS_AGENT4B_MODEL", "nichr0/schemalytics-gold-agent")
```

`os` is not yet imported in `planner.py`. Add it to the imports block at the top (after `from __future__ import annotations`):

```python
import os
```

- [ ] **Step 4: Pass model constants to the three agent calls**

**Agent 3** — `planner.py` lines 427–432. Change:
```python
        result = llm.query_structured(
            system=_AGENT3_SYSTEM,
            user=user_msg,
            response_model=_ClassificationList,
            max_tokens=_AGENT3_MAX_TOKENS_PER_BATCH,
        )
```
To:
```python
        result = llm.query_structured(
            system=_AGENT3_SYSTEM,
            user=user_msg,
            response_model=_ClassificationList,
            max_tokens=_AGENT3_MAX_TOKENS_PER_BATCH,
            model=_AGENT3_MODEL,
        )
```

**Agent 4a (Silver)** — `planner.py` lines 887–892. Change:
```python
    silver = llm.query_structured(
        system=_AGENT4_SILVER_SYSTEM,
        user=silver_user,
        response_model=_SilverPlan,
        max_tokens=silver_max_tokens,
    )
```
To:
```python
    silver = llm.query_structured(
        system=_AGENT4_SILVER_SYSTEM,
        user=silver_user,
        response_model=_SilverPlan,
        max_tokens=silver_max_tokens,
        model=_AGENT4A_MODEL,
    )
```

**Agent 4b (Gold)** — `planner.py` lines 932–937. Change:
```python
    gold_result = llm.query_structured(
        system=_AGENT4_GOLD_SYSTEM,
        user=gold_user,
        response_model=_GoldContainer,
        max_tokens=gold_max_tokens,
    )
```
To:
```python
    gold_result = llm.query_structured(
        system=_AGENT4_GOLD_SYSTEM,
        user=gold_user,
        response_model=_GoldContainer,
        max_tokens=gold_max_tokens,
        model=_AGENT4B_MODEL,
    )
```

- [ ] **Step 5: Run test to verify it passes**

```bash
pytest tests/test_integration.py::test_per_agent_models_configured -v
```
Expected: PASS

- [ ] **Step 6: Run full unit suite to check for regressions**

```bash
pytest tests/test_agents.py -v
```
Expected: all 13 tests pass.

- [ ] **Step 7: Commit**

```bash
git add schemalytics/planner.py tests/test_integration.py
git commit -m "feat: add per-agent fine-tuned model constants with env var overrides"
```

---

## Task 3: `_check_finetuned_models()` — availability check with user prompt

**Files:**
- Modify: `schemalytics/planner.py` (add `import subprocess`; add `_check_finetuned_models()`; call at top of `run_pipeline()`)
- Test: `tests/test_agents.py` (append 3 tests)

- [ ] **Step 1: Write the three failing tests**

Open [`tests/test_agents.py`](tests/test_agents.py). Append at the end of the file:

```python
# ── _check_finetuned_models tests ─────────────────────────────────────────────

class _FakeRun:
    """Minimal stand-in for subprocess.CompletedProcess."""
    def __init__(self, stdout: str, returncode: int = 0):
        self.stdout = stdout
        self.returncode = returncode


def test_check_finetuned_models_all_present(monkeypatch: pytest.MonkeyPatch) -> None:
    """No prompt or warning when all three fine-tuned models appear in ollama list."""
    import schemalytics.planner as planner_module

    ollama_output = (
        "nichr0/schemalytics-classification-agent  latest  abc123  1.2 GB\n"
        "nichr0/schemalytics-silver-agent           latest  def456  1.2 GB\n"
        "nichr0/schemalytics-gold-agent             latest  ghi789  1.2 GB\n"
    )
    monkeypatch.setattr(
        planner_module.subprocess, "run",
        lambda *a, **kw: _FakeRun(ollama_output),
    )
    planner_module._check_finetuned_models()  # must not raise


def test_check_finetuned_models_missing_warns_and_continues(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture,
) -> None:
    """Prints warning with pull command when a model is missing; patches global to base model on 'y'."""
    import schemalytics.planner as planner_module

    monkeypatch.setattr(
        planner_module.subprocess, "run",
        lambda *a, **kw: _FakeRun(""),  # empty — nothing pulled
    )
    monkeypatch.setattr("builtins.input", lambda _: "y")

    planner_module._check_finetuned_models()

    captured = capsys.readouterr()
    assert "ollama pull nichr0/schemalytics-classification-agent" in captured.out
    assert "ollama pull nichr0/schemalytics-silver-agent" in captured.out
    assert "ollama pull nichr0/schemalytics-gold-agent" in captured.out


def test_check_finetuned_models_abort_on_n(monkeypatch: pytest.MonkeyPatch) -> None:
    """Raises SystemExit(1) when the user answers 'n'."""
    import schemalytics.planner as planner_module

    monkeypatch.setattr(
        planner_module.subprocess, "run",
        lambda *a, **kw: _FakeRun(""),
    )
    monkeypatch.setattr("builtins.input", lambda _: "n")

    with pytest.raises(SystemExit):
        planner_module._check_finetuned_models()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_agents.py::test_check_finetuned_models_all_present \
       tests/test_agents.py::test_check_finetuned_models_missing_warns_and_continues \
       tests/test_agents.py::test_check_finetuned_models_abort_on_n -v
```
Expected: FAIL with `AttributeError: module 'schemalytics.planner' has no attribute 'subprocess'`

- [ ] **Step 3: Add `import subprocess` to `planner.py`**

Open [`schemalytics/planner.py`](schemalytics/planner.py). In the imports block, after `import os`, add:

```python
import subprocess
```

- [ ] **Step 4: Implement `_check_finetuned_models()`**

In [`schemalytics/planner.py`](schemalytics/planner.py), add the following function just before `run_pipeline()` (around line 1105, after `_show_plan_diff`):

```python
def _check_finetuned_models() -> None:
    """Check that fine-tuned Ollama models are pulled; warn and prompt if not.

    Skipped when SCHEMALYTICS_LLM_PROVIDER != 'ollama'.
    Only checks model names that start with 'nichr0/' (i.e. the fine-tuned defaults,
    not user overrides pointing at local models).
    """
    if llm.get_provider() != "ollama":
        return

    candidates = [
        ("Agent 3 (classification)", _AGENT3_MODEL),
        ("Agent 4a (silver plan)",   _AGENT4A_MODEL),
        ("Agent 4b (gold plan)",     _AGENT4B_MODEL),
    ]
    to_check = [(label, name) for label, name in candidates if name.startswith("nichr0/")]
    if not to_check:
        return

    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            print("Warning: 'ollama list' returned an error. Skipping model availability check.")
            return
        available = result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"Warning: could not run 'ollama list' ({exc}). Skipping model availability check.")
        return

    missing = [(label, name) for label, name in to_check if name not in available]
    if not missing:
        return

    print()
    for label, name in missing:
        print(f"Warning: fine-tuned model '{name}' is not pulled.")
        print(f"  → Run: ollama pull {name}")
        print(f"  → {label} will use {llm.OLLAMA_DEFAULT_MODEL} instead (quality may be lower).")
        print()

    answer = input("Continue anyway? [y/N] ").strip().lower()
    if answer != "y":
        raise SystemExit(1)

    # Patch module-level constants for this run so agent calls pick up the fallback.
    global _AGENT3_MODEL, _AGENT4A_MODEL, _AGENT4B_MODEL
    for _, name in missing:
        if name == _AGENT3_MODEL:
            _AGENT3_MODEL = llm.OLLAMA_DEFAULT_MODEL
        if name == _AGENT4A_MODEL:
            _AGENT4A_MODEL = llm.OLLAMA_DEFAULT_MODEL
        if name == _AGENT4B_MODEL:
            _AGENT4B_MODEL = llm.OLLAMA_DEFAULT_MODEL
```

- [ ] **Step 5: Call `_check_finetuned_models()` at the top of `run_pipeline()`**

In `run_pipeline()` (line 1107), add one call as the very first line of the function body, before the Agent 1 print:

```python
def run_pipeline(schema: Schema) -> tuple[ModelingPlan, PipelineContext, SemanticLayer] | None:
    """Run the full five-agent pipeline. Returns (ModelingPlan, PipelineContext) or None if cancelled."""
    _check_finetuned_models()

    # ── Agent 1: Industry Inference ────────────────────────────────────────────
    print(f"\nAgent 1 — Inferring industry and domain...  [{_ts()}]")
```

- [ ] **Step 6: Run the three new tests**

```bash
pytest tests/test_agents.py::test_check_finetuned_models_all_present \
       tests/test_agents.py::test_check_finetuned_models_missing_warns_and_continues \
       tests/test_agents.py::test_check_finetuned_models_abort_on_n -v
```
Expected: all 3 PASS.

- [ ] **Step 7: Run the full unit suite**

```bash
pytest tests/test_agents.py -v
```
Expected: all 16 tests pass.

- [ ] **Step 8: Commit**

```bash
git add schemalytics/planner.py tests/test_agents.py
git commit -m "feat: add _check_finetuned_models() startup check with user prompt"
```

---

## Task 4: Rewrite integration test — full pipeline end-to-end

**Files:**
- Modify: `tests/test_integration.py`

- [ ] **Step 1: Replace the `test_full_pipeline_northwind` stub**

Open [`tests/test_integration.py`](tests/test_integration.py). Replace the `pass` stub in `test_full_pipeline_northwind` with the full implementation:

```python
@integration_only
def test_full_pipeline_northwind(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: extract Northwind schema, run all 6 agents, generate dbt project.

    Prerequisites:
      - Ollama running with fine-tuned models pulled (or SCHEMALYTICS_AGENT*_MODEL overrides set)
      - Northwind Postgres at NORTHWIND_DSN (default: postgresql://postgres:postgres@localhost:5432/northwind)

    Run:
      SCHEMALYTICS_INTEGRATION=1 pytest tests/test_integration.py::test_full_pipeline_northwind -v
    """
    import schemalytics.planner as planner_module
    from schemalytics.extractors.postgres import extract_schema
    from schemalytics.generators.dbt import generate_dbt_project
    from schemalytics.planner import run_pipeline

    # Bypass 'ollama list' check — models are assumed available in this environment
    monkeypatch.setattr(planner_module, "_check_finetuned_models", lambda: None)
    # Auto-approve the Agent 5 refinement loop (press Enter = accept plan)
    monkeypatch.setattr("builtins.input", lambda _: "")

    # 1. Extract schema
    schema = extract_schema(NORTHWIND_DSN)
    assert len(schema.tables) > 0, "No tables extracted — is Northwind running?"

    # 2. Run the full 6-agent pipeline
    result = run_pipeline(schema)
    assert result is not None, "Pipeline returned None (user cancelled)"

    plan, ctx, semantic_layer = result

    # Plan sanity
    assert len(plan.bronze) > 0, "No bronze models generated"
    assert len(plan.bronze) == len(schema.tables), (
        f"Bronze count {len(plan.bronze)} != table count {len(schema.tables)}"
    )
    assert len(plan.dimensions) > 0 or len(plan.facts) > 0, "No silver models generated"

    # Semantic layer sanity
    assert len(semantic_layer.semantic_models) > 0, "Agent 6 returned no semantic models"

    # 3. Generate dbt project
    with tempfile.TemporaryDirectory() as tmpdir:
        project_path = generate_dbt_project(
            schema,
            plan,
            tmpdir,
            "northwind_test",
            business_type=ctx.business_type,
            context=ctx,
            semantic_layer=semantic_layer,
        )

        # Core structure
        assert (project_path / "dbt_project.yml").exists()
        assert (project_path / "models" / "bronze").exists()
        assert (project_path / "models" / "silver" / "dimensions").exists()
        assert (project_path / "models" / "silver" / "facts").exists()
        assert (project_path / "models" / "gold").exists()

        # Semantic layer output (new file, replaces old semantic_layer.yml)
        assert (project_path / "semantic_models.yml").exists(), (
            "semantic_models.yml not written — check _write_semantic_layer() in dbt.py"
        )

        # Bronze SQL count matches plan
        bronze_files = list((project_path / "models" / "bronze").glob("*.sql"))
        assert len(bronze_files) == len(plan.bronze), (
            f"Expected {len(plan.bronze)} bronze SQL files, got {len(bronze_files)}"
        )
```

- [ ] **Step 2: Verify the unit test still passes (no DB needed)**

```bash
pytest tests/test_integration.py::test_per_agent_models_configured -v
```
Expected: PASS.

- [ ] **Step 3: Commit**

```bash
git add tests/test_integration.py
git commit -m "test: rewrite integration test for 6-agent pipeline and semantic_models.yml"
```

---

## Task 5: Manual smoke test

- [ ] **Step 1: Confirm fine-tuned models are pulled**

```bash
ollama list | grep nichr0
```
Expected output (all three lines present):
```
nichr0/schemalytics-classification-agent  latest  ...
nichr0/schemalytics-silver-agent          latest  ...
nichr0/schemalytics-gold-agent            latest  ...
```
If any are missing, run `ollama pull <model-name>`.

- [ ] **Step 2: Start Northwind**

```bash
docker run -d -p 5432:5432 -e POSTGRES_PASSWORD=postgres ghcr.io/nichr0/northwind-postgres:latest
```

- [ ] **Step 3: Run integration test**

```bash
SCHEMALYTICS_INTEGRATION=1 \
NORTHWIND_DSN="postgresql://postgres:postgres@localhost:5432/northwind" \
pytest tests/test_integration.py -v
```
Expected: both tests PASS.

- [ ] **Step 4: Run full unit suite one final time**

```bash
pytest tests/test_agents.py tests/test_integration.py::test_per_agent_models_configured -v
```
Expected: all 17 tests pass.

- [ ] **Step 5: Final commit**

```bash
git add -p  # review any remaining unstaged changes
git commit -m "chore: verify e2e pipeline with fine-tuned models"
```
