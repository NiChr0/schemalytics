"""Schemalytics - Automated dbt project generation."""
from schemalytics.models import Schema, BusinessContext, ModelingPlan, PipelineContext, SemanticLayer
from schemalytics.extractors.postgres import extract_schema
from schemalytics.generators.dbt import generate_dbt_project

__version__ = "1.0.1"
__all__ = [
    "Schema",
    "BusinessContext",
    "ModelingPlan",
    "PipelineContext",
    "SemanticLayer",
    "extract_schema",
    "generate_dbt_project",
]
