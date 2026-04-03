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
