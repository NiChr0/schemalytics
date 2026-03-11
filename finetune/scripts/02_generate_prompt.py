#!/usr/bin/env python3
"""
Generate a Claude.ai labeling prompt from an extracted schema JSON.

Run from repo root:
    python finetune/scripts/02_generate_prompt.py finetune/extracted/sakila.json
"""

import sys
from pathlib import Path

if len(sys.argv) != 2:
    print("Usage: python finetune/scripts/02_generate_prompt.py <extracted_json_path>")
    sys.exit(1)

schema_path = Path(sys.argv[1])
if not schema_path.exists():
    print(f"ERROR: File not found: {schema_path}")
    sys.exit(1)

from schemalytics.models import Schema, PipelineContext
from schemalytics.planner import classify_by_fk_graph, _compact_schema_summary, _heuristic_summary

schema = Schema.model_validate_json(schema_path.read_text())

# Generic context — real business context is unknown for downloaded schemas
ctx = PipelineContext(
    industry="unknown",
    business_type="unknown",
    metrics=[],
    goals=[],
    grain="unknown",
    table_classifications=[],
)

heuristics = classify_by_fk_graph(schema)
compact_summary = _compact_schema_summary(schema)
heuristic_summary = _heuristic_summary(heuristics)

# Build the base_context string exactly as classify_tables() does
base_context = (
    f"Database schema:\n{compact_summary}\n\n"
    f"Heuristic pre-classifications:\n{heuristic_summary}\n\n"
    f"Business context:\n"
    f"  Industry: {ctx.industry} / {ctx.business_type}\n"
    f"  Metrics:  {', '.join(ctx.metrics)}\n"
    f"  Goals:    {', '.join(ctx.goals)}"
)

all_table_names = [t.name for t in schema.tables]
user_message = (
    base_context
    + f"\n\nClassify ONLY these {len(all_table_names)} tables "
    f"(skip all others): {all_table_names}"
)

print(f"Schema: {schema_path.stem}  |  Tables: {len(schema.tables)}")
print()
print("=== PASTE INTO CLAUDE.AI ===")
print()
print("You are a senior data engineer expert in Kimball dimensional modeling.")
print()
print("Classify each table in this database schema as one of:")
print('- "fact": transactional/event table (measures + FK keys to dimensions)')
print('- "dimension": descriptive entity table (attributes, looked up by facts)')
print('- "bridge": resolves many-to-many between facts and dimensions')
print('- "reference": small lookup/code table (status codes, types, categories)')
print()
print("For each table output:")
print("- table_name: exact table name")
print("- role: one of fact/dimension/bridge/reference")
print("- confidence: 1 (uncertain), 2 (moderate), 3 (certain)")
print("- reasoning: one sentence explaining why")
print("- needs_clarification: true only if ambiguous without business context")
print()
print(user_message)
print()
print('Respond ONLY with valid JSON in this exact structure — no preamble, no markdown:')
print('{')
print('  "classifications": [')
print('    {')
print('      "table_name": "orders",')
print('      "role": "fact",')
print('      "confidence": 3,')
print('      "reasoning": "Has FK keys to customers and products, contains order_date and amount measures.",')
print('      "needs_clarification": false')
print('    }')
print('  ]')
print('}')
print()
print("=== END PASTE ===")
