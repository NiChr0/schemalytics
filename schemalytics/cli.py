"""Schemalytics CLI."""
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
from schemalytics.industry_taxonomy import INDUSTRY_TAXONOMY


VALID_ROLES = ("fact", "dimension", "bridge", "skip")


def select_industry() -> tuple[str, dict]:
    """Let user select main industry and sub-industry from predefined list."""
    click.echo("\n" + "=" * 70)
    click.echo("INDUSTRY SELECTION")
    click.echo("=" * 70 + "\n")
    
    # Step 1: Select main industry
    click.echo("Available industries:\n")
    industries = list(INDUSTRY_TAXONOMY.keys())
    for idx, key in enumerate(industries, 1):
        click.echo(f"  {idx}. {INDUSTRY_TAXONOMY[key]['name']}")
    
    while True:
        choice = click.prompt("\nSelect industry number", type=int)
        if 1 <= choice <= len(industries):
            main_industry_key = industries[choice - 1]
            break
        click.echo(f"Invalid choice. Please select 1-{len(industries)}")
    
    main_industry = INDUSTRY_TAXONOMY[main_industry_key]
    click.echo(f"\n✓ Selected: {main_industry['name']}")
    
    # Step 2: Select sub-industry
    click.echo(f"\nAvailable sub-industries:\n")
    sub_industries = list(main_industry['sub_industries'].keys())
    for idx, key in enumerate(sub_industries, 1):
        click.echo(f"  {idx}. {main_industry['sub_industries'][key]['name']}")
    
    while True:
        choice = click.prompt("\nSelect sub-industry number", type=int)
        if 1 <= choice <= len(sub_industries):
            sub_industry_key = sub_industries[choice - 1]
            break
        click.echo(f"Invalid choice. Please select 1-{len(sub_industries)}")
    
    sub_industry = main_industry['sub_industries'][sub_industry_key]
    click.echo(f"✓ Selected: {sub_industry['name']}")
    
    # Return the full key and the sub-industry data
    full_key = f"{main_industry_key}_{sub_industry_key}"
    return full_key, sub_industry


def edit_list(items: list[str], item_type: str) -> list[str]:
    """Allow user to edit a list by adding/removing items."""
    current = items.copy()
    
    while True:
        click.echo(f"\nCurrent {item_type}:")
        for idx, item in enumerate(current, 1):
            click.echo(f"  {idx}. {item}")
        
        click.echo(f"\nOptions:")
        click.echo("  [a] Accept")
        click.echo("  [+] Add item")
        click.echo("  [-] Remove item (enter number)")
        
        action = click.prompt("Choose action", type=str).lower().strip()
        
        if action == "a":
            return current
        elif action == "+":
            new_item = click.prompt(f"Enter new {item_type[:-1]}")
            current.append(new_item.strip())
            click.echo(f"✓ Added: {new_item}")
        elif action == "-":
            if not current:
                click.echo("List is empty, nothing to remove")
                continue
            try:
                num = click.prompt(f"Enter number to remove (1-{len(current)})", type=int)
                if 1 <= num <= len(current):
                    removed = current.pop(num - 1)
                    click.echo(f"✓ Removed: {removed}")
                else:
                    click.echo(f"Invalid number")
            except:
                click.echo("Invalid input")
        else:
            # Try parsing as number for removal
            try:
                num = int(action)
                if 1 <= num <= len(current):
                    removed = current.pop(num - 1)
                    click.echo(f"✓ Removed: {removed}")
            except:
                click.echo("Invalid action. Use 'a', '+', or '-'")


def gather_context_interactively(schema: Schema) -> BusinessContext:
    """Gather business context with strict industry selection and editable suggestions."""
    
    # Step 1: Industry selection
    industry_key, sub_industry_data = select_industry()
    business_type = industry_key
    
    # Step 2: Show and edit entities
    click.echo("\n" + "=" * 70)
    click.echo("ENTITIES")
    click.echo("=" * 70)
    
    # Show detected tables
    detected_tables = [t.name for t in schema.tables]
    click.echo(f"\n🔍 Detected tables in your database ({len(detected_tables)}):")
    for idx, table in enumerate(detected_tables, 1):
        click.echo(f"  {idx}. {table}")
    
    # Show suggested entities
    suggested_entities = sub_industry_data['entities']
    click.echo(f"\n💡 Suggested entities for {sub_industry_data['name']}:")
    for entity in suggested_entities:
        click.echo(f"  • {entity}")
    
    click.echo("\nYou can accept these suggestions, or add/remove entities.")
    entities = edit_list(suggested_entities, "entities")
    
    # Step 3: Show and edit goals
    click.echo("\n" + "=" * 70)
    click.echo("ANALYTICAL GOALS")
    click.echo("=" * 70)
    
    suggested_goals = sub_industry_data['goals']
    click.echo(f"\n🎯 Suggested goals for {sub_industry_data['name']}:")
    for goal in suggested_goals:
        click.echo(f"  • {goal}")
    
    click.echo("\nYou can accept these suggestions, or add/remove goals.")
    goals = edit_list(suggested_goals, "goals")
    
    # Step 4: Show metrics (informational only, not editable)
    click.echo("\n" + "=" * 70)
    click.echo("METRICS (Auto-generated)")
    click.echo("=" * 70)
    
    suggested_metrics = sub_industry_data['metrics']
    click.echo(f"\n📊 Common metrics for {sub_industry_data['name']}:")
    for metric in suggested_metrics:
        click.echo(f"  • {metric}")
    click.echo("\n(These will be auto-generated in the Gold layer)")
    
    # Step 5: Temporal tracking
    click.echo("\n" + "=" * 70)
    click.echo("TEMPORAL TRACKING")
    click.echo("=" * 70)
    
    click.echo("\nOptions:")
    click.echo("  1. snapshot    - Current state only (SCD Type 1)")
    click.echo("  2. historical  - Track changes over time (SCD Type 2)")
    click.echo("  3. both        - Mixed approach")
    
    while True:
        choice = click.prompt("\nSelect option", type=int, default=2)
        if choice == 1:
            temporal = "snapshot"
            break
        elif choice == 2:
            temporal = "historical"
            break
        elif choice == 3:
            temporal = "both"
            break
        click.echo("Invalid choice. Please select 1, 2, or 3")
    
    # Step 6: Gold layer time grains
    click.echo("\n" + "=" * 70)
    click.echo("GOLD LAYER TIME GRAINS")
    click.echo("=" * 70)
    
    click.echo("\nSelect which time grains to generate for Gold aggregates:")
    click.echo("  1. Daily")
    click.echo("  2. Weekly")
    click.echo("  3. Monthly")
    click.echo("  4. Yearly")
    
    available_grains = ["daily", "weekly", "monthly", "yearly"]
    selected_grains = []
    
    grain_input = click.prompt(
        "\nEnter numbers separated by commas (e.g., '1,3,4' for daily, monthly, yearly)",
        default="1,3,4"
    )
    
    try:
        selections = [int(x.strip()) for x in grain_input.split(",")]
        for sel in selections:
            if 1 <= sel <= 4:
                grain = available_grains[sel - 1]
                if grain not in selected_grains:
                    selected_grains.append(grain)
        
        if not selected_grains:
            click.echo("⚠️  No valid grains selected, using default: daily, monthly, yearly")
            selected_grains = ["daily", "monthly", "yearly"]
        else:
            click.echo(f"✓ Selected grains: {', '.join(selected_grains)}")
    except:
        click.echo("⚠️  Invalid input, using default: daily, monthly, yearly")
        selected_grains = ["daily", "monthly", "yearly"]
    
    return BusinessContext(
        business_type=business_type,
        entities=entities,
        goals=goals,
        temporal=temporal,
        grain=",".join(selected_grains)  # Store as comma-separated string
    )


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
        # Build plan to show Gold models
        plan = build_plan_from_llm_output(schema, current_output, context)
        click.echo(format_plan_for_review([], current_output, plan.gold))
        
        choice = click.prompt(
            "\n[a]ccept / [e]dit / [r]eject",
            type=click.Choice(["a", "e", "r"], case_sensitive=False),
            show_choices=False
        )
        
        if choice == "a":
            return plan
        elif choice == "e":
            current_output = collect_user_edits(current_output)
        else:
            return None


@click.group()
@click.version_option(version="0.1.0")
def cli():
    """Schemalytics - Automated dbt project generation."""
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
    """Generate modeling plan (heuristics → LLM → Gold → user review)."""
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
@click.option("--context", "-x", "context_file", required=True, help="Context YAML file")
def build(schema_file: str, plan_file: str, output: str, name: str, context_file: str):
    """Build dbt project from modeling plan."""
    schema = Schema.model_validate_json(Path(schema_file).read_text())
    modeling_plan = ModelingPlan.model_validate(yaml.safe_load(Path(plan_file).read_text()))
    context = BusinessContext.model_validate(yaml.safe_load(Path(context_file).read_text()))
    
    project_path = generate_dbt_project(
        schema, modeling_plan, output, name, business_type=context.business_type
    )
    click.echo(f"Project created at {project_path}")


@click.command()
@click.option("--connection", "-c", required=True, help="PostgreSQL connection string")
@click.option("--output", "-o", default="./dbt_project", help="Output directory")
@click.option("--name", "-n", default="schemalytics_project", help="Project name")
@click.option("--context", "-x", "context_file", default=None, help="Context YAML file (optional)")
def generate(connection: str, output: str, name: str, context_file: str | None):
    """Full pipeline: extract → analyze → LLM → Gold → review/edit → generate."""
    # Extract
    click.echo("Step 1: Extracting schema...")
    schema = extract_schema(connection)
    click.echo(f"  Found {len(schema.tables)} tables")
    
    # Get or create context
    if context_file and Path(context_file).exists():
        click.echo(f"\nLoading context from {context_file}")
        context = BusinessContext.model_validate(yaml.safe_load(Path(context_file).read_text()))
    else:
        context = gather_context_interactively(schema)
        
        # Save context
        context_path = Path("context.yaml")
        context_path.write_text(yaml.dump(context.model_dump(), default_flow_style=False))
        click.echo(f"\n✓ Context saved to {context_path}")
    
    # Analyze
    click.echo("\nStep 2: Analyzing (heuristics + LLM validation + Gold generation)...")
    _, _, llm_output, _ = generate_plan_with_validation(schema, context)
    
    # Review/Edit
    click.echo("\nStep 3: Review proposed model (including Gold layer)")
    modeling_plan = user_review_loop(schema, context, llm_output)
    
    if not modeling_plan:
        click.echo("Aborted.")
        return
    
    # Generate
    click.echo(f"\nStep 4: Generating dbt project with semantic layer...")
    project_path = generate_dbt_project(
        schema, modeling_plan, output, name, business_type=context.business_type
    )
    
    click.echo(f"\nDone! Project: {project_path}")
    click.echo(f"  {len(modeling_plan.dimensions)} dimensions")
    click.echo(f"  {len(modeling_plan.facts)} facts")
    click.echo(f"  {len(modeling_plan.gold)} gold aggregates")
    click.echo(f"\nSemantic layer: {project_path}/semantic_layer.yml")


cli.add_command(extract)
cli.add_command(plan)
cli.add_command(build)
cli.add_command(generate)

if __name__ == "__main__":
    cli()