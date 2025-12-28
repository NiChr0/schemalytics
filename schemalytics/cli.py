"""DataForge CLI."""
import click
import yaml
from pathlib import Path

from schemalytics.models import Schema, BusinessContext, ModelingPlan
from schemalytics.extractors.postgres import extract_schema
from schemalytics.planner import (
    generate_plan, generate_plan_with_validation,
    build_plan_from_llm_output, format_plan_for_review
)
from schemalytics.generators.dbt import generate_dbt_project


VALID_ROLES = ("fact", "dimension", "bridge", "skip")


def collect_user_edits(llm_output: list[dict]) -> list[dict]:
    """Prompt user for edits to the LLM plan."""
    click.echo("\nEnter changes as: table_name=role (fact/dimension/bridge/skip)")
    click.echo("Leave blank when done.\n")
    
    table_map = {item["table"]: item for item in llm_output}
    
    while True:
        edit = click.prompt("Edit", default="", show_default=False)
        if not edit:
            break
        
        try:
            table, role = [x.strip() for x in edit.split("=")]
            if table not in table_map:
                click.echo(f"  Unknown table: {table}")
            elif role not in VALID_ROLES:
                click.echo(f"  Invalid role: {role} (use: {', '.join(VALID_ROLES)})")
            else:
                table_map[table]["role"] = role
                table_map[table]["reason"] = "User override"
                click.echo(f"  {table} → {role}")
        except ValueError:
            click.echo("  Format: table_name=role")
    
    return list(table_map.values())


def user_review_loop(schema: Schema, context: BusinessContext, llm_output: list[dict]) -> ModelingPlan | None:
    """Review loop: accept / edit / reject."""
    current_output = llm_output
    
    while True:
        click.echo(format_plan_for_review([], current_output))
        
        choice = click.prompt(
            "\n[a]ccept / [e]dit / [r]eject",
            type=click.Choice(["a", "e", "r"], case_sensitive=False),
            show_choices=False
        )
        
        if choice == "a":
            return build_plan_from_llm_output(schema, current_output, context)
        elif choice == "e":
            current_output = collect_user_edits(current_output)
        else:
            return None


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """DataForge - Automated dbt project generation."""
    pass


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="schema.json", help="Output file")
def extract(connection: str, output: str):
    """Extract schema from PostgreSQL database."""
    click.echo("Extracting schema...")
    schema = extract_schema(connection)
    Path(output).write_text(schema.model_dump_json(indent=2))
    click.echo(f"Saved {len(schema.tables)} tables to {output}")


@click.command()
@click.option("--schema", "-s", "schema_file", required=True, help="Schema JSON file")
@click.option("--context", "-c", "context_file", required=True, help="Context YAML file")
@click.option("--output", "-o", default="modeling_plan.yaml", help="Output file")
def plan(schema_file: str, context_file: str, output: str):
    """Generate modeling plan (heuristics → LLM → user review)."""
    schema = Schema.model_validate_json(Path(schema_file).read_text())
    context = BusinessContext.model_validate(yaml.safe_load(Path(context_file).read_text()))
    
    click.echo("Analyzing schema...")
    _, _, llm_output, _ = generate_plan_with_validation(schema, context)
    
    modeling_plan = user_review_loop(schema, context, llm_output)
    
    if modeling_plan:
        Path(output).write_text(yaml.dump(modeling_plan.model_dump(), default_flow_style=False))
        click.echo(f"Plan saved to {output}")
    else:
        click.echo("Aborted.")


@click.command()
@click.option("--schema", "-s", "schema_file", required=True, help="Schema JSON file")
@click.option("--plan", "-p", "plan_file", required=True, help="Modeling plan YAML file")
@click.option("--output", "-o", default="./dbt_project", help="Output directory")
@click.option("--name", "-n", default="schemalytics_project", help="Project name")
def build(schema_file: str, plan_file: str, output: str, name: str):
    """Build dbt project from modeling plan."""
    schema = Schema.model_validate_json(Path(schema_file).read_text())
    modeling_plan = ModelingPlan.model_validate(yaml.safe_load(Path(plan_file).read_text()))
    
    project_path = generate_dbt_project(schema, modeling_plan, output, name)
    click.echo(f"Project created at {project_path}")


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="./dbt_project", help="Output directory")
@click.option("--name", "-n", default="schemalytics_project", help="Project name")
@click.option("--business-type", "-b", default="generic", help="Business type")
def generate(connection: str, output: str, name: str, business_type: str):
    """Full pipeline: extract → analyze → review/edit → generate."""
    # Extract
    click.echo("Step 1: Extracting schema...")
    schema = extract_schema(connection)
    click.echo(f"  Found {len(schema.tables)} tables")
    
    # Analyze
    click.echo("\nStep 2: Analyzing (heuristics + LLM validation)...")
    context = BusinessContext(
        business_type=business_type,
        entities=[t.name for t in schema.tables],
        goals=["reporting"],
        temporal="historical",
        grain="transaction",
    )
    
    _, _, llm_output, _ = generate_plan_with_validation(schema, context)
    
    # Review/Edit
    click.echo("\nStep 3: Review proposed model")
    modeling_plan = user_review_loop(schema, context, llm_output)
    
    if not modeling_plan:
        click.echo("Aborted.")
        return
    
    # Generate
    click.echo(f"\nStep 4: Generating dbt project...")
    project_path = generate_dbt_project(schema, modeling_plan, output, name)
    
    click.echo(f"\nDone! Project: {project_path}")
    click.echo(f"  {len(modeling_plan.dimensions)} dimensions, {len(modeling_plan.facts)} facts")


cli.add_command(extract)
cli.add_command(plan)
cli.add_command(build)
cli.add_command(generate)

if __name__ == "__main__":
    cli()
