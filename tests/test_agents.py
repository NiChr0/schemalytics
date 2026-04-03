"""Unit tests for the five-agent pipeline.

Each test mocks schemalytics.llm.query_structured so no real LLM is needed.
"""
from __future__ import annotations

from unittest.mock import patch

import pytest

from schemalytics.models import (
    Column,
    DimensionPlan,
    FactPlan,
    ForeignKey,
    GoldPlan,
    IndustryInference,
    MetricDefinition,
    MetricsSuggestion,
    ModelingPlan,
    PipelineContext,
    Schema,
    Table,
    TableClassificationResult,
)
from schemalytics.planner import (
    classify_by_fk_graph,
    classify_tables,
    generate_modeling_plan,
    infer_industry,
    refine_modeling_plan,
    suggest_metrics,
)

# ── Fixtures ───────────────────────────────────────────────────────────────────

@pytest.fixture()
def northwind_schema() -> Schema:
    """Minimal Northwind-like schema fragment for testing."""
    return Schema(
        tables=[
            Table(
                name="customers",
                schema_name="public",
                columns=[
                    Column(name="customer_id", data_type="integer"),
                    Column(name="company_name", data_type="varchar"),
                    Column(name="contact_name", data_type="varchar"),
                    Column(name="country", data_type="varchar"),
                ],
                primary_key=["customer_id"],
                foreign_keys=[],
            ),
            Table(
                name="orders",
                schema_name="public",
                columns=[
                    Column(name="order_id", data_type="integer"),
                    Column(name="customer_id", data_type="integer"),
                    Column(name="order_date", data_type="date"),
                    Column(name="freight", data_type="numeric"),
                ],
                primary_key=["order_id"],
                foreign_keys=[
                    ForeignKey(
                        column="customer_id",
                        references_table="customers",
                        references_column="customer_id",
                    )
                ],
            ),
            Table(
                name="order_details",
                schema_name="public",
                columns=[
                    Column(name="order_id", data_type="integer"),
                    Column(name="product_id", data_type="integer"),
                    Column(name="quantity", data_type="integer"),
                    Column(name="unit_price", data_type="numeric"),
                    Column(name="discount", data_type="numeric"),
                ],
                primary_key=["order_id", "product_id"],
                foreign_keys=[
                    ForeignKey(
                        column="order_id",
                        references_table="orders",
                        references_column="order_id",
                    ),
                    ForeignKey(
                        column="product_id",
                        references_table="products",
                        references_column="product_id",
                    ),
                ],
            ),
            Table(
                name="products",
                schema_name="public",
                columns=[
                    Column(name="product_id", data_type="integer"),
                    Column(name="product_name", data_type="varchar"),
                    Column(name="unit_price", data_type="numeric"),
                    Column(name="category_id", data_type="integer"),
                ],
                primary_key=["product_id"],
                foreign_keys=[],
            ),
        ]
    )


@pytest.fixture()
def high_confidence_industry() -> IndustryInference:
    return IndustryInference(
        industry="retail",
        business_type="ecommerce",
        confidence=3,
        reasoning="Schema has customers, orders, products — classic ecommerce pattern.",
        needs_clarification=False,
    )


@pytest.fixture()
def low_confidence_industry() -> IndustryInference:
    return IndustryInference(
        industry="unknown",
        business_type="unclear",
        confidence=1,
        reasoning="Schema is ambiguous — tables have no clear domain signal.",
        needs_clarification=True,
    )


@pytest.fixture()
def sample_metrics() -> MetricsSuggestion:
    return MetricsSuggestion(
        metrics=["total_revenue", "order_count", "average_order_value"],
        goals=["daily_revenue_reporting", "product_sales_analysis"],
        suggested_grain="order_line",
        confidence=3,
        reasoning="Standard ecommerce metrics derived from orders and order_details.",
        needs_clarification=False,
        clarification_question=None,
    )


@pytest.fixture()
def sample_classifications(northwind_schema: Schema) -> list[TableClassificationResult]:
    return [
        TableClassificationResult(
            table_name="customers",
            role="dimension",
            confidence=3,
            reasoning="Referenced by orders, no outgoing FKs.",
            needs_clarification=False,
        ),
        TableClassificationResult(
            table_name="orders",
            role="fact",
            confidence=3,
            reasoning="Has outgoing FK to customers, contains measures.",
            needs_clarification=False,
        ),
        TableClassificationResult(
            table_name="order_details",
            role="fact",
            confidence=3,
            reasoning="Bridge between orders and products with measures.",
            needs_clarification=False,
        ),
        TableClassificationResult(
            table_name="products",
            role="dimension",
            confidence=3,
            reasoning="Referenced by order_details, no outgoing FKs.",
            needs_clarification=False,
        ),
    ]


@pytest.fixture()
def sample_context(
    high_confidence_industry: IndustryInference,
    sample_metrics: MetricsSuggestion,
    sample_classifications: list[TableClassificationResult],
) -> PipelineContext:
    return PipelineContext(
        industry=high_confidence_industry.industry,
        business_type=high_confidence_industry.business_type,
        metrics=sample_metrics.metrics,
        goals=sample_metrics.goals,
        grain=sample_metrics.suggested_grain,
        table_classifications=sample_classifications,
    )


@pytest.fixture()
def sample_modeling_plan() -> ModelingPlan:
    return ModelingPlan(
        bronze=["customers", "orders", "order_details", "products"],
        dimensions=[
            DimensionPlan(
                name="dim_customers",
                source_table="customers",
                scd_type=2,
                grain="one row per customer per version",
                columns=["customer_id", "company_name", "contact_name", "country"],
            ),
            DimensionPlan(
                name="dim_products",
                source_table="products",
                scd_type=1,
                grain="one row per product",
                columns=["product_id", "product_name", "unit_price"],
            ),
        ],
        facts=[
            FactPlan(
                name="fct_order_details",
                source_table="order_details",
                grain="one row per order line",
                dimension_keys=["order_id", "product_id"],
                measures=["quantity", "unit_price", "discount"],
                date_column="order_date",
            ),
        ],
        gold=[
            GoldPlan(
                name="agg_daily_revenue",
                source_fact="fct_order_details",
                grain="daily",
                dimensions=["product_id"],
                metrics=[
                    MetricDefinition(
                        name="total_revenue",
                        aggregation="SUM",
                        column="unit_price",
                        description="Sum of unit prices",
                    )
                ],
                date_column="order_date",
                description="Daily revenue by product",
            )
        ],
    )


# ── FK Graph Heuristics ────────────────────────────────────────────────────────

def test_classify_by_fk_graph_identifies_facts_and_dims(northwind_schema: Schema) -> None:
    results = classify_by_fk_graph(northwind_schema)
    by_name = {r.table.name: r for r in results}

    # customers: 1 incoming FK from orders, 0 outgoing → dimension
    assert by_name["customers"].role == "dimension"
    # order_details: 2 outgoing FKs (orders, products) → fact
    assert by_name["order_details"].role == "fact"
    # products: 0 FKs in or out (in this fragment) → dimension
    assert by_name["products"].role == "dimension"


def test_classify_by_fk_graph_returns_all_tables(northwind_schema: Schema) -> None:
    results = classify_by_fk_graph(northwind_schema)
    result_names = {r.table.name for r in results}
    schema_names = {t.name for t in northwind_schema.tables}
    assert result_names == schema_names


# ── Agent 1: Industry Inference ────────────────────────────────────────────────

def test_infer_industry_returns_valid_model(
    northwind_schema: Schema,
    high_confidence_industry: IndustryInference,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=high_confidence_industry):
        result = infer_industry(northwind_schema)

    assert isinstance(result, IndustryInference)
    assert result.industry == "retail"
    assert result.confidence == 3
    assert not result.needs_clarification


def test_infer_industry_low_confidence_sets_needs_clarification(
    northwind_schema: Schema,
    low_confidence_industry: IndustryInference,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=low_confidence_industry):
        result = infer_industry(northwind_schema)

    assert result.confidence == 1
    assert result.needs_clarification is True


def test_infer_industry_passes_user_feedback_in_prompt(
    northwind_schema: Schema,
    high_confidence_industry: IndustryInference,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=high_confidence_industry) as mock_qs:
        infer_industry(northwind_schema, user_feedback="We are a B2B food distributor")

    call_kwargs = mock_qs.call_args
    user_arg = call_kwargs[1]["user"] if call_kwargs[1] else call_kwargs[0][1]
    assert "B2B food distributor" in user_arg


# ── Agent 2: Metrics Suggestion ────────────────────────────────────────────────

def test_suggest_metrics_returns_valid_model(
    northwind_schema: Schema,
    high_confidence_industry: IndustryInference,
    sample_metrics: MetricsSuggestion,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=sample_metrics):
        result = suggest_metrics(northwind_schema, high_confidence_industry)

    assert isinstance(result, MetricsSuggestion)
    assert len(result.metrics) > 0
    assert result.suggested_grain == "order_line"


def test_suggest_metrics_low_confidence_sets_clarification_question(
    northwind_schema: Schema,
    high_confidence_industry: IndustryInference,
) -> None:
    low_conf_metrics = MetricsSuggestion(
        metrics=["some_metric"],
        goals=["some_goal"],
        suggested_grain="unknown",
        confidence=1,
        reasoning="Cannot determine grain from schema.",
        needs_clarification=True,
        clarification_question="What is the primary reporting grain for your business?",
    )
    with patch("schemalytics.planner.llm.query_structured", return_value=low_conf_metrics):
        result = suggest_metrics(northwind_schema, high_confidence_industry)

    assert result.needs_clarification is True
    assert result.clarification_question is not None


# ── Agent 3: Table Classification ─────────────────────────────────────────────

def test_classify_tables_returns_all_tables(
    northwind_schema: Schema,
    sample_context: PipelineContext,
    sample_classifications: list[TableClassificationResult],
) -> None:
    from pydantic import BaseModel

    class _ClassificationList(BaseModel):
        classifications: list[TableClassificationResult]

    mock_return = _ClassificationList(classifications=sample_classifications)

    with patch("schemalytics.planner.llm.query_structured", return_value=mock_return):
        results = classify_tables(northwind_schema, sample_context)

    assert len(results) == len(sample_classifications)
    result_names = {r.table_name for r in results}
    assert "customers" in result_names
    assert "orders" in result_names


def test_classify_tables_low_confidence_sets_needs_clarification(
    northwind_schema: Schema,
    sample_context: PipelineContext,
) -> None:
    low_conf_classifications = [
        TableClassificationResult(
            table_name="customers",
            role="dimension",
            confidence=1,
            reasoning="Ambiguous — no clear signal.",
            needs_clarification=True,
        ),
    ]

    from pydantic import BaseModel

    class _ClassificationList(BaseModel):
        classifications: list[TableClassificationResult]

    mock_return = _ClassificationList(classifications=low_conf_classifications)

    with patch("schemalytics.planner.llm.query_structured", return_value=mock_return):
        results = classify_tables(northwind_schema, sample_context)

    assert results[0].needs_clarification is True
    assert results[0].confidence == 1


# ── Agent 4: Modeling Plan Generation ─────────────────────────────────────────

def test_generate_modeling_plan_returns_valid_model(
    northwind_schema: Schema,
    sample_context: PipelineContext,
    sample_modeling_plan: ModelingPlan,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=sample_modeling_plan):
        result = generate_modeling_plan(northwind_schema, sample_context)

    assert isinstance(result, ModelingPlan)
    assert len(result.bronze) > 0
    assert len(result.dimensions) > 0
    assert len(result.facts) > 0


def test_generate_modeling_plan_bronze_includes_all_tables(
    northwind_schema: Schema,
    sample_context: PipelineContext,
    sample_modeling_plan: ModelingPlan,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=sample_modeling_plan):
        result = generate_modeling_plan(northwind_schema, sample_context)

    schema_tables = {t.name for t in northwind_schema.tables}
    assert schema_tables.issubset(set(result.bronze))


# ── Agent 5: Refinement ────────────────────────────────────────────────────────

def test_refine_modeling_plan_returns_valid_model(
    northwind_schema: Schema,
    sample_context: PipelineContext,
    sample_modeling_plan: ModelingPlan,
) -> None:
    refined = ModelingPlan(
        bronze=sample_modeling_plan.bronze,
        dimensions=sample_modeling_plan.dimensions,
        facts=sample_modeling_plan.facts,
        gold=[],  # user removed all gold models
    )

    with patch("schemalytics.planner.llm.query_structured", return_value=refined):
        result = refine_modeling_plan(
            sample_modeling_plan,
            feedback="Remove all gold aggregates",
            schema=northwind_schema,
            context=sample_context,
        )

    assert isinstance(result, ModelingPlan)
    assert len(result.gold) == 0


def test_refine_modeling_plan_passes_feedback_in_prompt(
    northwind_schema: Schema,
    sample_context: PipelineContext,
    sample_modeling_plan: ModelingPlan,
) -> None:
    with patch("schemalytics.planner.llm.query_structured", return_value=sample_modeling_plan) as mock_qs:
        refine_modeling_plan(
            sample_modeling_plan,
            feedback="Split dim_customers into B2B and B2C",
            schema=northwind_schema,
            context=sample_context,
        )

    call_kwargs = mock_qs.call_args
    user_arg = call_kwargs[1]["user"] if call_kwargs[1] else call_kwargs[0][1]
    assert "B2B and B2C" in user_arg


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
