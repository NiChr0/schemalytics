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
    assert len(semantic_layer.metrics) >= 0  # zero is allowed for sparse schemas; non-None confirms structure

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
