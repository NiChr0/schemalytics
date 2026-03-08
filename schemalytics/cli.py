"""CLI entry point for Schemalytics."""
import click
from pathlib import Path

from schemalytics.extractors.postgres import extract_schema
from schemalytics.generators.dbt import generate_dbt_project
from schemalytics.planner import run_pipeline


@click.group()
@click.version_option(version="0.1.3")
def cli():
    """Schemalytics - Automated dbt project generation with an agentic pipeline."""


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="./dbt_project", help="Output directory")
@click.option("--name", "-n", default="schemalytics_project", help="Project name")
def generate(connection: str, output: str, name: str):
    """Extract schema, run the agent pipeline, and generate a dbt project."""
    print("\n" + "=" * 64)
    print("SCHEMALYTICS — AGENTIC DATA MODEL GENERATION")
    print("=" * 64)

    # Step 1: Extract schema
    print("\nExtracting database schema...")
    schema = extract_schema(connection)
    print(f"  Found {len(schema.tables)} tables")

    # Step 2: Run agent pipeline (Agents 1–5)
    result = run_pipeline(schema)

    if not result:
        print("\nGeneration cancelled.")
        return

    modeling_plan, pipeline_ctx = result

    # Step 3: Generate dbt project
    print("\nGenerating dbt project...")
    project_path = generate_dbt_project(
        schema,
        modeling_plan,
        output,
        name,
        business_type=pipeline_ctx.business_type,
        context=pipeline_ctx,
    )

    print("\n" + "=" * 64)
    print("SUCCESS")
    print("=" * 64)
    print(f"\nProject created at: {project_path}")
    print(f"  {len(modeling_plan.bronze)} bronze models")
    print(f"  {len(modeling_plan.dimensions)} silver dimensions")
    print(f"  {len(modeling_plan.facts)} silver facts")
    print(f"  {len(modeling_plan.gold)} gold aggregates")
    print("\nNext steps:")
    print(f"  cd {project_path}")
    print("  dbt deps")
    print("  dbt run")


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
