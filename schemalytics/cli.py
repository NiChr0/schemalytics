"""CLI entry point for Schemalytics."""
import click
from pathlib import Path
from rich.console import Console
from rich.panel import Panel

from schemalytics.extractors.postgres import extract_schema
from schemalytics.generators.dbt import generate_dbt_project
from schemalytics.planner import run_pipeline

console = Console()


@click.group()
@click.version_option(version="0.2.0")
def cli():
    """Schemalytics - Automated dbt project generation with an agentic pipeline."""


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="./dbt_project", help="Output directory")
@click.option("--name", "-n", default="schemalytics_project", help="Project name")
def generate(connection: str, output: str, name: str):
    """Extract schema, run the agent pipeline, and generate a dbt project."""
    console.print()
    console.rule("[bold cyan]SCHEMALYTICS — AGENTIC DATA MODEL GENERATION[/]")
    console.print()

    # Step 1: Extract schema
    with console.status("[bold]Extracting database schema...[/]"):
        schema = extract_schema(connection)
    console.print(f"  [green]✓[/] Found [bold]{len(schema.tables)}[/] tables")

    # Step 2: Run agent pipeline (Agents 1–5)
    result = run_pipeline(schema)

    if not result:
        console.print("\n[yellow]Generation cancelled.[/]")
        return

    modeling_plan, pipeline_ctx = result

    # Step 3: Generate dbt project
    with console.status("[bold]Generating dbt project...[/]"):
        project_path = generate_dbt_project(
            schema,
            modeling_plan,
            output,
            name,
            business_type=pipeline_ctx.business_type,
            context=pipeline_ctx,
        )

    console.print(Panel(
        f"[bold]Project created at:[/] {project_path}\n\n"
        f"  [cyan]•[/] {len(modeling_plan.bronze)} bronze models\n"
        f"  [cyan]•[/] {len(modeling_plan.dimensions)} silver dimensions\n"
        f"  [cyan]•[/] {len(modeling_plan.facts)} silver facts\n"
        f"  [cyan]•[/] {len(modeling_plan.gold)} gold aggregates\n\n"
        "[bold]Next steps:[/]\n"
        f"  [dim]cd {project_path}[/]\n"
        "  [dim]dbt deps[/]\n"
        "  [dim]dbt run[/]",
        title="[bold green]SUCCESS[/]",
        border_style="green",
    ))


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
