#!/usr/bin/env python3
"""
Auto-label Agent 4b (Gold plan) training examples using Claude Sonnet.

Reads labeled silver files from finetune/labeled_silver/ and for each:
  1. Parses the sanitized Silver facts from the assistant content.
  2. Rebuilds the exact Agent 4b user message using the stored context_block.
  3. Asks Claude to generate Gold aggregation models.
  4. Saves as a training record: {messages: [system, user, assistant]}.

Run label_silver.py first, then run this script from repo root:
    python finetune/scripts/label_gold.py
"""

import json
import os
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from schemalytics.models import DerivedMeasure, FactPlan
from schemalytics.planner import _AGENT4_GOLD_SYSTEM

# ── Config ─────────────────────────────────────────────────────────────────────

INPUT_DIR = Path("finetune/labeled_silver")
OUTPUT_DIR = Path("finetune/labeled_gold")
OUTPUT_DIR.mkdir(exist_ok=True)

JSON_ONLY = (
    "\n\nIMPORTANT: Output ONLY valid JSON. "
    "No markdown, no code fences, no explanation. "
    "Start your response with {."
)

# ── Helpers ────────────────────────────────────────────────────────────────────

def parse_facts(silver_content: str) -> list[FactPlan]:
    """Parse sanitized silver assistant JSON → list of FactPlan objects."""
    data = json.loads(silver_content)
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
    return facts


def _fact_summary_line(f: FactPlan) -> str:
    """Exact same format as _fact_summary_line() in production planner.py."""
    dm_str = (
        ", derived_measures=["
        + ", ".join(f"{dm.name}={dm.expression}" for dm in f.derived_measures)
        + "]"
    ) if f.derived_measures else ""
    return (
        f"  {f.name}: source={f.source_table}, "
        f"dim_keys={f.dimension_keys}, measures={f.measures}"
        f"{dm_str}, date={f.date_column}"
    )


def build_gold_user_message(facts: list[FactPlan], context_block: str) -> str:
    """Build the exact user message Agent 4b receives in production."""
    fact_summary = "\n".join(_fact_summary_line(f) for f in facts)
    return (
        f"Silver facts:\n{fact_summary}\n\n"
        f"Pipeline context:\n{context_block}"
    )


def generate_gold(
    client: anthropic.Anthropic, user_msg: str, n_facts: int
) -> dict:
    """Call Claude with the Agent 4b system prompt; return parsed JSON."""
    max_tokens = 6000
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=max_tokens,
        system=_AGENT4_GOLD_SYSTEM + JSON_ONLY,
        messages=[{"role": "user", "content": user_msg}],
    )
    raw = next((b.text for b in response.content if hasattr(b, "text")), "")
    start, end = raw.find("{"), raw.rfind("}") + 1
    if start == -1:
        raise ValueError(f"No JSON in gold response: {repr(raw[:300])}")
    return json.loads(raw[start:end])


def label_silver_record(
    client: anthropic.Anthropic, record: dict
) -> dict:
    """Generate one Agent 4b training example from a silver training record."""
    messages = record["messages"]
    context_block = record.get("_meta", {}).get("context_block", "")

    # Parse sanitized Silver facts (stored in assistant turn of silver record)
    facts = parse_facts(messages[2]["content"])
    if not facts:
        raise ValueError("No facts found in silver record — skipping")

    # Build the exact production gold user message
    user_msg = build_gold_user_message(facts, context_block)

    # Get gold plan from Claude
    gold_raw = generate_gold(client, user_msg, len(facts))

    # Normalise: ensure the response has a top-level "gold" key
    if "gold" not in gold_raw:
        # Claude sometimes returns the array directly or wraps it differently
        if isinstance(gold_raw, list):
            gold_raw = {"gold": gold_raw}
        else:
            # Try to find any list value in the dict
            for v in gold_raw.values():
                if isinstance(v, list):
                    gold_raw = {"gold": v}
                    break
            else:
                gold_raw = {"gold": []}

    return {
        "messages": [
            {"role": "system", "content": _AGENT4_GOLD_SYSTEM},
            {"role": "user", "content": user_msg},
            {"role": "assistant", "content": json.dumps(gold_raw, ensure_ascii=False)},
        ],
    }


# ── Main ───────────────────────────────────────────────────────────────────────

def main() -> None:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    client = anthropic.Anthropic(api_key=api_key)

    silver_files = sorted(INPUT_DIR.glob("*.jsonl"))
    if not silver_files:
        print(f"No silver files found in {INPUT_DIR}/")
        print("Run label_silver.py first.")
        return

    print(f"Found {len(silver_files)} silver examples to generate gold from")

    errors: list[str] = []
    for i, path in enumerate(silver_files):
        out_path = OUTPUT_DIR / path.name
        if out_path.exists():
            print(f"  [{i+1}/{len(silver_files)}] SKIP {path.stem} (already done)")
            continue

        try:
            record = json.loads(path.read_text(encoding="utf-8").strip())
            gold_record = label_silver_record(client, record)

            n_gold = len(json.loads(gold_record["messages"][2]["content"]).get("gold", []))
            out_path.write_text(
                json.dumps(gold_record, ensure_ascii=False) + "\n", encoding="utf-8"
            )
            print(f"  [{i+1}/{len(silver_files)}] OK   {path.stem} ({n_gold} gold models)")
        except Exception as e:
            print(f"  [{i+1}/{len(silver_files)}] ERR  {path.stem}: {e}")
            errors.append(path.stem)

        time.sleep(0.5)

    print(f"\nDone. Errors: {len(errors)}")
    if errors:
        print("Failed:", errors)


if __name__ == "__main__":
    main()
