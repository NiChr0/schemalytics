"""Schemalytics - Automated dbt project generation."""
from schemalytics.models import Schema, BusinessContext, ModelingPlan
from schemalytics.extractors.postgres import extract_schema
from schemalytics.generators.dbt import generate_dbt_project

__version__ = "0.2.0"
__all__ = [
    "Schema",
    "BusinessContext", 
    "ModelingPlan",
    "extract_schema",
    "generate_dbt_project",
]
