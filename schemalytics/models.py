"""Data models for schema and modeling plan."""
from pydantic import BaseModel
from typing import Literal, Optional


class Column(BaseModel):
    name: str
    data_type: str
    nullable: bool = True
    description: Optional[str] = None


class ForeignKey(BaseModel):
    column: str
    references_table: str
    references_column: str


class Table(BaseModel):
    name: str
    schema_name: str = "public"
    columns: list[Column]
    primary_key: Optional[list[str]] = None
    foreign_keys: list[ForeignKey] = []
    description: Optional[str] = None


class Schema(BaseModel):
    tables: list[Table]


class BusinessContext(BaseModel):
    business_type: str  # ecommerce, saas, etc.
    entities: list[str]  # customers, orders, products
    goals: list[str]  # revenue_reporting, cohort_analysis
    temporal: str = "historical"  # snapshot, historical, both
    grain: str = "transaction"  # transaction, daily, monthly


class DimensionPlan(BaseModel):
    name: str
    source_table: str
    scd_type: int = 1
    grain: str
    columns: list[str] = []  # auto-filled from schema by _sanitize_plan; LLM must leave empty


class DerivedMeasure(BaseModel):
    """A measure computed from an expression of source columns.

    Rendered as ``expression AS name`` in the Silver fact SELECT so that Gold
    models can reference it by ``name`` without re-deriving the expression.
    """
    name: str        # SQL alias, e.g. "line_total"
    expression: str  # SQL expression, e.g. "orderqty * unitprice"


class FactPlan(BaseModel):
    name: str
    source_table: str
    grain: str
    dimension_keys: list[str]
    measures: list[str]              # bare numeric column names only
    derived_measures: list[DerivedMeasure] = []  # computed columns: expression AS name
    date_column: str
    factless: bool = False  # True when fact has no measures (factless fact table)


class MetricDefinition(BaseModel):
    name: str
    aggregation: Literal["SUM", "COUNT", "COUNT_DISTINCT", "AVG", "MIN", "MAX"]
    column: str
    description: str


class GoldPlan(BaseModel):
    name: str
    source_fact: str  # which fact table to aggregate
    grain: str  # "daily", "monthly", "yearly"
    dimensions: list[str]  # FK column names on the source fact table to group by (e.g. "customer_id", "product_id") — NOT dimension model names
    metrics: list[MetricDefinition]  # aggregated measures
    date_column: str
    description: str


class ModelingPlan(BaseModel):
    bronze: list[str]  # table names for passthrough
    dimensions: list[DimensionPlan]
    facts: list[FactPlan]
    gold: list[GoldPlan] = []


# ── Agent output models ────────────────────────────────────────────────────────

class IndustryInference(BaseModel):
    """Agent 1 output: inferred industry and business domain from schema metadata."""
    industry: str
    business_type: str
    confidence: int  # 1, 2, or 3
    reasoning: str
    needs_clarification: bool


class MetricsSuggestion(BaseModel):
    """Agent 2 output: suggested metrics, goals, and grain derived from the schema."""
    metrics: list[str]
    goals: list[str]
    suggested_grain: str
    confidence: int  # 1, 2, or 3
    reasoning: str
    needs_clarification: bool
    clarification_question: Optional[str] = None  # only when needs_clarification=True


class TableClassificationResult(BaseModel):
    """Agent 3 output: classification of a single table."""
    table_name: str
    role: str  # "fact", "dimension", "bridge", "reference"
    confidence: int  # 1, 2, or 3
    reasoning: str
    needs_clarification: bool


class PipelineContext(BaseModel):
    """Accumulated context passed between agents after Agents 1-3 complete."""
    industry: str
    business_type: str
    metrics: list[str]
    goals: list[str]
    grain: str
    table_classifications: list[TableClassificationResult]