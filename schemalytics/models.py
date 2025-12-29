"""Data models for schema and modeling plan."""
from pydantic import BaseModel
from typing import Optional


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
    columns: list[str]


class FactPlan(BaseModel):
    name: str
    source_table: str
    grain: str
    dimension_keys: list[str]
    measures: list[str]
    date_column: str


class MetricDefinition(BaseModel):
    name: str
    aggregation: str  # SUM, COUNT, AVG, etc.
    column: str
    description: str


class GoldPlan(BaseModel):
    name: str
    source_fact: str  # which fact table to aggregate
    grain: str  # "daily", "monthly", "yearly"
    dimensions: list[str]  # group by dimensions
    metrics: list[MetricDefinition]  # aggregated measures
    date_column: str
    description: str


class ModelingPlan(BaseModel):
    bronze: list[str]  # table names for passthrough
    dimensions: list[DimensionPlan]
    facts: list[FactPlan]
    gold: list[GoldPlan] = []