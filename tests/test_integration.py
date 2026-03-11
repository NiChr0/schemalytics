"""Integration test: full agent pipeline against Northwind via Docker.

Requires:
  - Ollama running at localhost:11434 with qwen3-8b-data pulled
  - Northwind Postgres: docker run -p 5432:5432 -e POSTGRES_PASSWORD=postgres
      ghcr.io/nichr0/northwind-postgres:latest

Run with:
  SCHEMALYTICS_LLM_PROVIDER=ollama pytest tests/test_integration.py -v
"""
from __future__ import annotations

import os
import tempfile

import pytest

NORTHWIND_DSN = os.environ.get(
    "NORTHWIND_DSN", "postgresql://postgres:mypassword@localhost:5432/northwind"
)

pytestmark = pytest.mark.skipif(
    os.environ.get("SCHEMALYTICS_INTEGRATION") != "1",
    reason="Set SCHEMALYTICS_INTEGRATION=1 to run integration tests",
)


def test_full_pipeline_northwind(monkeypatch: pytest.MonkeyPatch) -> None:
    """End-to-end: extract Northwind schema, run agent pipeline, generate dbt project."""
    from schemalytics.extractors.postgres import extract_schema
    from schemalytics.generators.dbt import generate_dbt_project
    from schemalytics.planner import (
        classify_tables,
        generate_modeling_plan,
        infer_industry,
        suggest_metrics,
    )
    from schemalytics.models import PipelineContext as PCtx

    # 1. Extract schema
    schema = extract_schema(NORTHWIND_DSN)
    assert len(schema.tables) > 0, "No tables extracted — is Northwind running?"

    # 2. Agent 1
    industry = infer_industry(schema)
    assert industry.industry  # non-empty string
    assert 1 <= industry.confidence <= 3

    # 3. Agent 2
    metrics = suggest_metrics(schema, industry)
    assert len(metrics.metrics) > 0
    assert 1 <= metrics.confidence <= 3

    # 4. Partial context for Agent 3
    partial_ctx = PCtx(
        industry=industry.industry,
        business_type=industry.business_type,
        metrics=metrics.metrics,
        goals=metrics.goals,
        grain=metrics.suggested_grain,
        table_classifications=[],
    )

    # 5. Agent 3
    classifications = classify_tables(schema, partial_ctx)
    assert len(classifications) == len(schema.tables)
    roles = {c.role for c in classifications}
    assert roles.issubset({"fact", "dimension", "bridge", "reference"})

    # 6. Full context
    context = PCtx(
        industry=industry.industry,
        business_type=industry.business_type,
        metrics=metrics.metrics,
        goals=metrics.goals,
        grain=metrics.suggested_grain,
        table_classifications=classifications,
    )

    # 7. Agent 4
    plan = generate_modeling_plan(schema, context)
    assert len(plan.bronze) > 0
    schema_table_names = {t.name for t in schema.tables}
    assert schema_table_names.issubset(set(plan.bronze)), (
        "Agent 4 missed some source tables in bronze"
    )

    # 8. Generate dbt project
    with tempfile.TemporaryDirectory() as tmpdir:

        class _ContextAdapter:
            goals: list[str] = []

        project_path = generate_dbt_project(
            schema,
            plan,
            tmpdir,
            "northwind_test",
            business_type=industry.business_type,
            context=_ContextAdapter(),
        )

        assert (project_path / "dbt_project.yml").exists()
        assert (project_path / "models" / "bronze").exists()
        assert (project_path / "models" / "silver" / "dimensions").exists()
        assert (project_path / "models" / "silver" / "facts").exists()
        assert (project_path / "models" / "gold").exists()
        assert (project_path / "semantic_layer.yml").exists()

        bronze_files = list((project_path / "models" / "bronze").glob("*.sql"))
        assert len(bronze_files) == len(plan.bronze), (
            f"Expected {len(plan.bronze)} bronze SQL files, got {len(bronze_files)}"
        )
