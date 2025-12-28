"""DataForge - Automated dbt project generation."""
from schemalytics.models import Schema, BusinessContext, ModelingPlan
from schemalytics.extractors.postgres import extract_schema
from schemalytics.planner import generate_plan
from schemalytics.generators.dbt import generate_dbt_project

__version__ = "0.1.0"
__all__ = [
    "Schema",
    "BusinessContext", 
    "ModelingPlan",
    "extract_schema",
    "generate_plan",
    "generate_dbt_project",
]
