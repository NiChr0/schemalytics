"""Updated CLI with interactive refinement loop."""
import click
import yaml
from pathlib import Path

from schemalytics.models import Schema, BusinessContext, ModelingPlan
from schemalytics.extractors.postgres import extract_schema
from schemalytics.generators.dbt import generate_dbt_project

# Import new functions
from schemalytics.planner import (
    interactive_refinement_loop,
    classify_by_fk_graph,
    gather_context_interactively,
)


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """Schemalytics - Automated dbt project generation with interactive refinement."""
    pass


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="./dbt_project", help="Output directory")
@click.option("--name", "-n", default="schemalytics_project", help="Project name")
@click.option("--context", "-x", "context_file", default=None, help="Context YAML file (optional)")
def generate(connection: str, output: str, name: str, context_file: str | None):
    """Full pipeline with INTERACTIVE REFINEMENT: extract → detailed plan → refine → approve → generate."""
    
    print("\n" + "=" * 80)
    print("SCHEMALYTICS - INTERACTIVE DATA MODEL GENERATION")
    print("=" * 80)
    
    # Step 1: Extract schema
    print("\n📥 STEP 1: EXTRACTING DATABASE SCHEMA")
    print("-" * 80)
    schema = extract_schema(connection)
    print(f"  ✓ Found {len(schema.tables)} tables")
    
    # Step 2: Get or create context
    print("\n🎯 STEP 2: BUSINESS CONTEXT")
    print("-" * 80)
    if context_file and Path(context_file).exists():
        print(f"  Loading context from {context_file}")
        context = BusinessContext.model_validate(yaml.safe_load(Path(context_file).read_text()))
        print(f"  ✓ Industry: {context.business_type}")
        print(f"  ✓ Goals: {', '.join(context.goals[:3])}")
    else:
        context = gather_context_interactively(schema)
        
        # Save context
        context_path = Path("context.yaml")
        context_path.write_text(yaml.dump(context.model_dump(), default_flow_style=False))
        print(f"\n  ✓ Context saved to {context_path}")
    
    # Step 3: Heuristic classification
    print("\n🔍 STEP 3: INITIAL CLASSIFICATION (FK GRAPH ANALYSIS)")
    print("-" * 80)
    heuristic_classifications = classify_by_fk_graph(schema)
    
    fact_count = sum(1 for c in heuristic_classifications if c.role == "fact")
    dim_count = sum(1 for c in heuristic_classifications if c.role == "dimension")
    print(f"  ✓ Identified {fact_count} potential facts, {dim_count} potential dimensions")
    
    # Step 4: Interactive refinement loop
    print("\n🔄 STEP 4: INTERACTIVE PLAN REFINEMENT")
    print("-" * 80)
    print("  The AI will generate a detailed plan with:")
    print("  • Exact table names (bronze_*, dim_*, fct_*, gold_*)")
    print("  • Data types and grains")
    print("  • Foreign key relationships")
    print("  • Measures and metrics")
    print("\n  You can refine the plan using natural language feedback.")
    
    modeling_plan = interactive_refinement_loop(schema, context, heuristic_classifications)
    
    if not modeling_plan:
        print("\n✗ Generation cancelled.")
        return
    
    # Step 5: Generate dbt project
    print("\n🏗️  STEP 5: GENERATING DBT PROJECT")
    print("-" * 80)
    project_path = generate_dbt_project(
        schema, modeling_plan, output, name, 
        business_type=context.business_type,
        context=context
    )
    
    print(f"\n{'='*80}")
    print("✅ SUCCESS!")
    print(f"{'='*80}")
    print(f"\nProject created at: {project_path}")
    print(f"\nContents:")
    print(f"  • {len(modeling_plan.bronze)} bronze models (raw passthrough)")
    print(f"  • {len(modeling_plan.dimensions)} silver dimensions")
    print(f"  • {len(modeling_plan.facts)} silver facts")
    print(f"  • {len(modeling_plan.gold)} gold aggregates")
    print(f"\nSemantic layer: {project_path}/semantic_layer.yml")
    print(f"\nNext steps:")
    print(f"  1. cd {project_path}")
    print(f"  2. Configure profiles.yml with your database connection")
    print(f"  3. dbt deps  # Install dependencies")
    print(f"  4. dbt run   # Build all models")
    print(f"\n{'='*80}")


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="schema.json", help="Output file")
def extract(connection: str, output: str):
    """Extract schema from PostgreSQL database (standalone)."""
    click.echo("Extracting schema...")
    schema = extract_schema(connection)
    Path(output).write_text(schema.model_dump_json(indent=2))
    click.echo(f"Saved {len(schema.tables)} tables to {output}")


cli.add_command(extract)
cli.add_command(generate)


if __name__ == "__main__":
    cli()