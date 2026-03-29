#!/usr/bin/env python3
"""
Auto-label Agent 4a (Silver plan) training examples using Claude Sonnet.

For each extracted schema:
  1. Claude → agents 1+2+3 combined: industry, metrics, goals, grain, table classifications.
  2. Claude → Agent 4a label: Silver plan (bronze + dimensions + facts).
  3. Sanitize the plan against the schema (strip hallucinated columns).
  4. Save as a training record: {messages: [system, user, assistant], _meta: {context_block}}.

Run from repo root:
    python finetune/scripts/label_silver.py
"""

import json
import os
import sys
import time
from pathlib import Path

import anthropic

# Add repo root to path so we can import schemalytics
ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from schemalytics.models import (
    Column, DerivedMeasure, DimensionPlan, FactPlan, ForeignKey,
    ModelingPlan, PipelineContext, Schema, Table, TableClassificationResult,
)
from schemalytics.planner import (
    _AGENT4_SILVER_SYSTEM,
    _numeric_cols_hint,
    _sanitize_plan,
    _schema_summary,
)

# ── Config ─────────────────────────────────────────────────────────────────────

EXTRACTED_DIRS = [
    Path("finetune/extracted_complex"),
    Path("finetune/extracted"),
    Path("finetune/extracted_spider"),
    Path("finetune/extracted_new"),
]
MIN_TABLES = 5  # skip trivial schemas with fewer tables
OUTPUT_DIR = Path("finetune/labeled_silver")
OUTPUT_DIR.mkdir(exist_ok=True)

JSON_ONLY = (
    "\n\nIMPORTANT: Output ONLY valid JSON. "
    "No markdown, no code fences, no explanation. "
    "Start your response with {."
)

# ── Combined context prompt (Agents 1 + 2 + 3 in one call) ────────────────────

_CONTEXT_SYSTEM = """\
You are a data engineering expert analyzing a database schema to plan a dbt data warehouse.

Given a database schema (table names, column names with data types, FK relationships), return a
single JSON object:

{
  "industry": "...",
  "business_type": "...",
  "metrics": ["..."],
  "goals": ["..."],
  "grain": "...",
  "table_classifications": [
    {
      "table_name": "...",
      "role": "fact|dimension|bridge|reference",
      "confidence": 1|2|3,
      "reasoning": "...",
      "needs_clarification": false
    }
  ]
}

Field guidance:
- industry: e.g. "retail", "healthcare", "manufacturing", "software", "hospitality"
- business_type: e.g. "ecommerce", "saas", "hospital", "erp", "analytics"
- metrics: 3-6 relevant business metric names in snake_case
- goals: 2-4 analytical goal names in snake_case
- grain: primary reporting grain, e.g. "order_line", "transaction", "daily", "subscription"
- reasoning: ≤8 words per table

Classification rules:
- FACT: records a business event; has a date column + numeric measures + FKs to dimensions.
  Header tables (salesorderheader, invoiceheader) ARE facts — they record transactions.
- DIMENSION: describes a business entity; has descriptive text/categorical attributes.
  Product catalogs, employee/person tables are always DIMENSION even with outgoing FKs.
- BRIDGE: pure many-to-many resolver; has ONLY two FK columns (+ maybe surrogate PK) and
  almost no other attributes. If it has 3+ descriptive attributes it is NOT a bridge.
- REFERENCE: small standalone lookup with no FKs at all (status_codes, currencies, regions).
"""


# ── Helpers ────────────────────────────────────────────────────────────────────

def load_schema(path: Path) -> Schema:
    data = json.loads(path.read_text(encoding="utf-8"))
    return Schema(**data)


def _schema_for_context(schema: Schema) -> str:
    """Compact schema text for the context-generation call (includes data types + FKs)."""
    lines = []
    for t in schema.tables:
        fk_map = {fk.column: fk.references_table for fk in t.foreign_keys}
        parts = []
        for c in t.columns[:20]:
            dtype = c.data_type.lower().split("(")[0]
            suffix = f"→{fk_map[c.name]}" if c.name in fk_map else f":{dtype}"
            parts.append(f"{c.name}{suffix}")
        lines.append(f"  {t.name}({', '.join(parts)})")
    return "\n".join(lines)


def generate_context(
    client: anthropic.Anthropic, schema: Schema, db_id: str
) -> PipelineContext:
    """Single Claude call → PipelineContext (agents 1+2+3 combined)."""
    user_msg = f"Database: {db_id}\n\nSchema:\n{_schema_for_context(schema)}"
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=_CONTEXT_SYSTEM + JSON_ONLY,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1:
        raise ValueError(f"No JSON in context response: {repr(raw[:300])}")
    data = json.loads(raw[start:end])

    table_classifications = [
        TableClassificationResult(**tc) for tc in data["table_classifications"]
    ]
    return PipelineContext(
        industry=data["industry"],
        business_type=data["business_type"],
        metrics=data["metrics"],
        goals=data["goals"],
        grain=data["grain"],
        table_classifications=table_classifications,
    )


def build_silver_user_message(
    schema: Schema, context: PipelineContext
) -> tuple[str, str]:
    """Build the exact user message Agent 4a receives in production.

    Returns (user_message, context_block) — context_block is stored in _meta
    so label_gold.py can reconstruct the gold user message without re-running
    context generation.
    """
    table_roles = "\n".join(
        f"  {c.table_name}: {c.role}" for c in context.table_classifications
    )
    all_tables = [t.name for t in schema.tables]
    context_block = (
        f"  Industry: {context.industry} / {context.business_type}\n"
        f"  Metrics:  {', '.join(context.metrics)}\n"
        f"  Goals:    {', '.join(context.goals)}\n"
        f"  Grain:    {context.grain}"
    )
    numeric_hint = _numeric_cols_hint(schema, context)
    user_msg = (
        f"Database schema:\n{_schema_summary(schema)}\n\n"
        f"All source tables (all must appear in bronze): {all_tables}\n\n"
        f"Pipeline context:\n{context_block}\n\n"
        f"Table roles (from Agent 3):\n{table_roles}"
        + (f"\n\n{numeric_hint}" if numeric_hint else "")
    )
    return user_msg, context_block


def generate_silver(client: anthropic.Anthropic, user_msg: str) -> dict:
    """Call Claude with the Agent 4a system prompt; return parsed JSON."""
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=8000,
        system=_AGENT4_SILVER_SYSTEM + JSON_ONLY,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1:
        raise ValueError(f"No JSON in silver response: {repr(raw[:300])}")
    return json.loads(raw[start:end])


def parse_silver_to_plan(data: dict) -> ModelingPlan:
    """Parse the raw silver JSON dict into a ModelingPlan pydantic object."""
    dimensions = [
        DimensionPlan(
            name=d["name"],
            source_table=d["source_table"],
            scd_type=d.get("scd_type", 1),
            grain=d.get("grain", "entity"),
            columns=d.get("columns", []),
        )
        for d in data.get("dimensions", [])
    ]
    facts = []
    for f in data.get("facts", []):
        dm_list = [DerivedMeasure(**dm) for dm in f.get("derived_measures", [])]
        facts.append(FactPlan(
            name=f["name"],
            source_table=f["source_table"],
            grain=f.get("grain", "transaction"),
            dimension_keys=f.get("dimension_keys", []),
            measures=f.get("measures", []),
            derived_measures=dm_list,
            date_column=f.get("date_column", ""),
            factless=f.get("factless", False),
        ))
    return ModelingPlan(
        bronze=data.get("bronze", []),
        dimensions=dimensions,
        facts=facts,
        gold=[],
    )


def label_schema(
    client: anthropic.Anthropic, db_id: str, schema: Schema
) -> dict:
    """Generate one Agent 4a training example for a schema."""
    # Step 1: Claude (agents 1+2) + trained model (agent 3)
    context = generate_context(client, schema, db_id)
    time.sleep(0.3)

    # Step 2: Build the exact production user message
    user_msg, context_block = build_silver_user_message(schema, context)

    # Step 3: Get silver plan from Claude
    silver_raw = generate_silver(client, user_msg)

    # Step 4: Parse + sanitize (ground truth = what production code would validate)
    raw_plan = parse_silver_to_plan(silver_raw)
    sanitized = _sanitize_plan(raw_plan, schema)

    # Step 5: Build assistant content.
    # Dimension columns are reset to [] — the system prompt instructs the model
    # to output [] for columns (sanitizer auto-fills them in production).
    # Fact measures/dimension_keys/derived_measures use sanitized values so the
    # model learns to output correct column names.
    training_dims = [
        {**d.model_dump(), "columns": []} for d in sanitized.dimensions
    ]
    assistant_content = json.dumps({
        "bronze": sanitized.bronze,
        "dimensions": training_dims,
        "facts": [f.model_dump() for f in sanitized.facts],
    }, ensure_ascii=False)

    return {
        "messages": [
            {"role": "system", "content": _AGENT4_SILVER_SYSTEM},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": assistant_content},
        ],
        # _meta is not used during training; stored for label_gold.py
        "_meta": {
            "db_id": db_id,
            "context_block": context_block,
        },
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)

    # Collect all schema files; deduplicate by stem (extracted/ vs extracted_complex/)
    seen: set[str] = set()
    schema_files: list[Path] = []
    for dir_path in EXTRACTED_DIRS:
        if not dir_path.exists():
            continue
        for path in sorted(dir_path.glob("*.json")):
            if path.stem not in seen:
                seen.add(path.stem)
                schema_files.append(path)

    print(f"Found {len(schema_files)} schemas to label for Agent 4a (Silver)")

    errors: list[str] = []
    for i, path in enumerate(schema_files):
        out_path = OUTPUT_DIR / f"{path.stem}.jsonl"
        if out_path.exists():
            print(f"  [{i+1}/{len(schema_files)}] SKIP {path.stem} (already done)")
            continue

        try:
            schema = load_schema(path)
            if not schema.tables:
                print(f"  [{i+1}/{len(schema_files)}] SKIP {path.stem} (empty)")
                continue
            if len(schema.tables) < MIN_TABLES:
                print(f"  [{i+1}/{len(schema_files)}] SKIP {path.stem} ({len(schema.tables)} tables < {MIN_TABLES})")
                continue

            record = label_schema(client, path.stem, schema)
            out_path.write_text(
                json.dumps(record, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            silver_data = json.loads(record["messages"][2]["content"])
            n_facts = len(silver_data.get("facts", []))
            n_dims = len(silver_data.get("dimensions", []))
            print(
                f"  [{i+1}/{len(schema_files)}] OK   {path.stem} "
                f"({len(schema.tables)} tables, {n_dims} dims, {n_facts} facts)"
            )
        except Exception as e:
            print(f"  [{i+1}/{len(schema_files)}] ERR  {path.stem}: {e}")
            errors.append(path.stem)

        time.sleep(0.5)

    print(f"\nDone. Errors: {len(errors)}")
    if errors:
        print("Failed:", errors)


if __name__ == "__main__":
    main()
