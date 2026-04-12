"""Agentic pipeline: five focused agents for schema-to-dbt planning."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime

import re as _re

from rich.console import Console
from rich.panel import Panel
from rich.table import Table as _RichTable

from schemalytics import llm
from schemalytics.models import (
    DerivedMeasure,
    DimensionPlan,
    FactPlan,
    GoldPlan,
    IndirectKey,
    IndustryInference,
    MetricDefinition,
    MetricsSuggestion,
    ModelingPlan,
    PipelineContext,
    Schema,
    Table,
    TableClassificationResult,
)


def _ts() -> str:
    """Current wall-clock time as HH:MM:SS for inline progress stamps."""
    return datetime.now().strftime('%H:%M:%S')


console = Console()


# ── Per-agent model selection ──────────────────────────────────────────────────
# Fine-tuned models are the defaults. Override via env var for ablation testing.
_AGENT3_MODEL  = os.environ.get("SCHEMALYTICS_AGENT3_MODEL",  "nichr0/schemalytics-classification-agent")
_AGENT4A_MODEL = os.environ.get("SCHEMALYTICS_AGENT4A_MODEL", "nichr0/schemalytics-silver-agent")
_AGENT4B_MODEL = os.environ.get("SCHEMALYTICS_AGENT4B_MODEL", "nichr0/schemalytics-gold-agent")


# ── FK Graph Heuristics ────────────────────────────────────────────────────────

class TableClassification:
    """Heuristic classification result for a single table (used by Agent 3 as prior)."""

    def __init__(self, table: Table, role: str, confidence: str, reason: str) -> None:
        self.table = table
        self.role = role
        self.confidence = confidence
        self.reason = reason


def _non_fk_column_count(table: Table) -> int:
    """Count columns that are not FK columns and not the primary key."""
    fk_cols = {fk.column for fk in table.foreign_keys}
    pk_cols = set(table.primary_key or [])
    return sum(1 for c in table.columns if c.name not in fk_cols and c.name not in pk_cols)


_DATE_COLUMN_TYPES = {
    "date", "timestamp", "timestamptz", "datetime",
    "timestamp without time zone", "timestamp with time zone",
}

# Audit/system timestamps — present in almost every table, carry no business event meaning.
# Excluding them from transaction-date detection prevents bridge/dimension tables that only
# have a modifieddate from being promoted to "fact" by the FK heuristic.
_AUDIT_TIMESTAMP_NAMES = {
    "modifieddate", "modified_date", "updated_at", "updatedat",
    "last_modified", "last_modified_at", "last_updated_at", "last_updated",
    "date_modified", "modified_on", "updated_on", "rowversion", "timestamp",
    "created_at", "createdat", "datecreated", "datemodified",
}


def _has_transaction_date(table: Table) -> bool:
    """Return True if the table has a BUSINESS event date/timestamp column.

    Checks column data type first (reliable regardless of naming convention),
    but skips columns whose name is a known audit/system timestamp — those are
    present in nearly every table and do not signal a business transaction.
    Falls back to name-pattern matching for columns with unresolved types.
    """
    for col in table.columns:
        if (col.data_type.lower() in _DATE_COLUMN_TYPES
                and col.name.lower() not in _AUDIT_TIMESTAMP_NAMES):
            return True
    # Name-pattern fallback for unresolved types: ends with 'date' or '_at',
    # but not an audit timestamp name.
    col_names = {c.name.lower() for c in table.columns}
    event_cols = col_names - _AUDIT_TIMESTAMP_NAMES
    return any(name.endswith("date") or name.endswith("_at") for name in event_cols)


def classify_by_fk_graph(schema: Schema) -> list[TableClassification]:
    """Classify tables as fact/dimension/bridge using FK graph heuristics."""
    incoming_fks: dict[str, int] = {}
    outgoing_fks: dict[str, int] = {}

    for table in schema.tables:
        name = table.name
        outgoing_fks[name] = len(table.foreign_keys)
        incoming_fks.setdefault(name, 0)
        for fk in table.foreign_keys:
            incoming_fks[fk.references_table] = incoming_fks.get(fk.references_table, 0) + 1

    results = []
    for table in schema.tables:
        name = table.name
        incoming = incoming_fks.get(name, 0)
        outgoing = outgoing_fks.get(name, 0)
        non_fk_cols = _non_fk_column_count(table)

        if outgoing >= 2 and incoming == 0:
            # Pure junction/bridge: only FK columns, no descriptive attributes
            if non_fk_cols <= 1:
                role, confidence, reason = (
                    "bridge",
                    "high",
                    f"Has {outgoing} outgoing FKs, 0 incoming, {non_fk_cols} non-FK columns "
                    "(junction table — no descriptive attributes)",
                )
            else:
                role, confidence, reason = (
                    "fact",
                    "high",
                    f"Has {outgoing} outgoing FKs, no incoming FKs, {non_fk_cols} measure/attribute columns",
                )
        elif incoming >= 2 and outgoing == 0:
            role, confidence, reason = (
                "dimension",
                "high",
                f"Has {incoming} incoming FKs, no outgoing FKs (referenced by other tables)",
            )
        elif incoming >= 1 and outgoing >= 1:
            # Distinguish facts from snowflake dimensions:
            # A fact with both incoming and outgoing FKs typically has many outgoing FKs
            # (to multiple dimensions) AND a transaction date column.
            # A snowflake dimension has outgoing FKs to lookup tables but no transaction date.
            if outgoing >= 2 and _has_transaction_date(table):
                role, confidence, reason = (
                    "fact",
                    "medium",
                    f"Has {outgoing} outgoing and {incoming} incoming FKs with a transaction date "
                    "column — likely a fact table (Agent 3 should verify).",
                )
            else:
                role, confidence, reason = (
                    "dimension",
                    "medium",
                    f"Has {outgoing} outgoing and {incoming} incoming FKs, no transaction date — "
                    "likely a snowflake dimension. Agent 3 should verify.",
                )
        elif outgoing == 1 and incoming == 0:
            role, confidence, reason = (
                "dimension",
                "low",
                "Has 1 outgoing FK, no incoming (ambiguous — assuming dimension)",
            )
        elif outgoing == 0 and incoming == 1:
            role, confidence, reason = (
                "dimension",
                "medium",
                "No outgoing FKs, 1 incoming FK (likely dimension)",
            )
        else:
            role, confidence, reason = (
                "reference",
                "low",
                "No foreign keys (standalone lookup table — assuming reference)",
            )

        results.append(TableClassification(table=table, role=role, confidence=confidence, reason=reason))

    return results


# ── Schema Summary Helper ──────────────────────────────────────────────────────

def _compact_schema_summary(schema: Schema) -> str:
    """Minimal schema for agents that only need table/column names (no FK details)."""
    lines = []
    for t in schema.tables:
        cols = ", ".join(c.name for c in t.columns[:12])
        lines.append(f"  {t.name}({cols})")
    return "\n".join(lines)


def _fmt_row_count(n: int | None) -> str:
    """Format a row count as a compact human-readable string."""
    if n is None:
        return ""
    if n >= 1_000_000:
        return f" [{n/1_000_000:.1f}M rows]"
    if n >= 1_000:
        return f" [{n/1_000:.1f}K rows]"
    return f" [{n} rows]"


def _agent3_schema_fmt(tables: list) -> str:
    """Schema format matching Agent 3 training data: col→ref_table inline for FK columns.

    Row counts (from pg_stat_user_tables) are appended when available so the
    classifier can distinguish high-volume fact tables from low-cardinality dimensions.
    """
    lines = []
    for t in tables:
        fk_map = {fk.column: fk.references_table for fk in t.foreign_keys}
        col_parts = []
        for c in t.columns[:12]:
            col_parts.append(f"{c.name}→{fk_map[c.name]}" if c.name in fk_map else c.name)
        lines.append(f"  {t.name}{_fmt_row_count(t.row_count)}({', '.join(col_parts)})")
    return "\n".join(lines)


def _schema_summary(schema: Schema) -> str:
    """Compact schema representation for LLM prompts."""
    lines = []
    for t in schema.tables:
        cols = ", ".join(c.name for c in t.columns[:15])
        fks = ", ".join(f"{fk.column}→{fk.references_table}" for fk in t.foreign_keys)
        line = f"  {t.name}: columns=[{cols}]"
        if fks:
            line += f", fks=[{fks}]"
        lines.append(line)
    return "\n".join(lines)



def _heuristic_summary(heuristics: list[TableClassification]) -> str:
    lines = [
        f"  {h.table.name}: {h.role} (confidence={h.confidence}) — {h.reason}"
        for h in heuristics
    ]
    return "\n".join(lines)


# ── Agent 1: Industry + Domain Inference ──────────────────────────────────────

_AGENT1_SYSTEM = """\
You are a data engineer who infers the industry and business domain from database schema metadata.
Reason solely from table names, column names, and FK relationships — never rely on hardcoded taxonomies.

Few-shot examples:

Schema: customers(customer_id, email, loyalty_points), orders(order_id, customer_id, total_amount, ordered_at), products(product_id, sku, price)
→ industry: "retail", business_type: "ecommerce", confidence: 3

Schema: patients(patient_id, dob, diagnosis_code), appointments(appointment_id, patient_id, doctor_id, scheduled_at), insurance_claims(claim_id, patient_id, amount)
→ industry: "healthcare", business_type: "hospital_management", confidence: 3

Schema: accounts(account_id, plan_type, mrr), subscriptions(subscription_id, account_id, started_at, churned_at), feature_flags(flag_id, account_id, enabled)
→ industry: "software", business_type: "saas", confidence: 3

Identify ALL business domains present in the schema, not just the most prominent one. If the schema
contains tables for Sales, Production, Purchasing, and HR, report the primary industry AND mention
all sub-domains in your reasoning. This ensures all relevant metrics are captured in later stages.

When the schema is ambiguous or the domain is unusual, set needs_clarification=True and confidence < 3.
Always set confidence=1 if you are genuinely uncertain after reasoning.
"""


def infer_industry(schema: Schema, user_feedback: str | None = None) -> IndustryInference:
    """Agent 1 — infer industry and business domain from schema metadata."""
    user_msg = f"Database schema:\n{_compact_schema_summary(schema)}"
    if user_feedback:
        user_msg += f"\n\nUser correction / clarification: {user_feedback}"

    return llm.query_structured(
        system=_AGENT1_SYSTEM,
        user=user_msg,
        response_model=IndustryInference,
        max_tokens=512,
    )


# ── Agent 2: Metrics + Goals Suggestion ───────────────────────────────────────

_AGENT2_SYSTEM = """\
You are a data analyst who suggests relevant metrics, analytical goals, and reporting grain from
a database schema and its inferred industry context. Derive suggestions from the actual column names
— do not use generic preset lists.

CRITICAL: The inferred industry and business type (provided in the user message) is your PRIMARY
guide. Suggest metrics that business stakeholders in that industry care about — revenue, retention,
conversion, engagement — not internal operational metrics like employee headcount, HR activity,
or system administration counts. If the schema contains both business-facing and operational tables,
focus exclusively on the business-facing ones when selecting metrics and goals.

IMPORTANT: Respond with actual string values for metrics and goals. Do NOT output a schema definition
or property descriptions. Output a JSON object with real metric names like "total_revenue", real goal
names like "daily_revenue_reporting", a real grain like "order_line", a confidence integer (1, 2, or 3),
and a reasoning string.

GRAIN RULE: `suggested_grain` must be a business description, NOT a table name.
  WRONG: suggested_grain: "salesorderdetail"
  RIGHT:  suggested_grain: "one row per order line item"

METRIC RULE: Do NOT suggest subscription-economy metrics (MRR, ARR, monthly recurring revenue,
churn rate, LTV) unless the business_type is explicitly 'saas' or 'subscription'. For manufacturing,
retail, or mixed domains suggest domain-appropriate metrics instead (e.g. production yield,
order fill rate, inventory turnover, scrap rate, work order completion rate).

Few-shot examples:

Schema: orders(order_id, customer_id, total_amount, discount, ordered_at), order_items(item_id, order_id, product_id, quantity, unit_price), employees(employee_id, name, hire_date)
Industry: retail/ecommerce
→ metrics: ["total_revenue", "average_order_value", "items_per_order", "discount_rate"]
→ goals: ["daily_revenue_reporting", "product_sales_mix", "customer_purchase_frequency"]
→ suggested_grain: "order_line", confidence: 3, needs_clarification: false
NOTE: employees is an operational table — do NOT include HR metrics like headcount.

Schema: subscriptions(sub_id, account_id, plan, mrr, started_at, churned_at), events(event_id, account_id, event_type, occurred_at)
Industry: software/saas
→ metrics: ["monthly_recurring_revenue", "churn_rate", "active_subscriptions", "event_count_per_account"]
→ goals: ["mrr_trend_analysis", "churn_cohort_analysis", "feature_adoption"]
→ suggested_grain: "subscription", confidence: 3, needs_clarification: false

When the correct grain or metrics are uncertain, set needs_clarification=true with a clarification_question.
"""


def suggest_metrics(
    schema: Schema,
    industry: IndustryInference,
    user_feedback: str | None = None,
) -> MetricsSuggestion:
    """Agent 2 — suggest metrics, goals, and grain based on schema and inferred domain."""
    user_msg = (
        f"Database schema:\n{_compact_schema_summary(schema)}\n\n"
        f"Inferred industry: {industry.industry} / {industry.business_type}\n"
        f"Reasoning: {industry.reasoning}"
    )
    if user_feedback:
        user_msg += f"\n\nUser correction / clarification: {user_feedback}"

    return llm.query_structured(
        system=_AGENT2_SYSTEM,
        user=user_msg,
        response_model=MetricsSuggestion,
        max_tokens=512,
    )


# ── Agent 3: Table Classification ─────────────────────────────────────────────

_AGENT3_SYSTEM = """\
You are a data modelling expert who classifies database tables as "fact", "dimension", "bridge", or "reference".

You receive:
  1. The full database schema with column and FK details.
  2. Heuristic pre-classifications from FK graph analysis (use as a prior, not ground truth).
  3. Business context (industry, metrics, goals).

Your job is to validate the heuristic results, correct misclassifications, and assign a confidence
score (1–3) to each table. Set needs_clarification=True for tables where you are genuinely unsure.

Definitions:
  - FACT: Records a business event or transaction. Has a date column + measures (quantities, amounts,
    rates) + FKs to dimensions. Examples: order_details, orders, transactions, events, sessions.
  - DIMENSION: Describes a business entity. Has many descriptive text/categorical attributes. May have
    outgoing FKs to other dimensions (snowflake). Examples: customers, products, employees, categories.
  - BRIDGE: Resolves a many-to-many relationship. Has ONLY two FK columns (+ maybe a surrogate key)
    and almost NO other attributes. Examples: employee_territories, user_roles, product_tags.
  - REFERENCE: Small standalone lookup table with no FKs in or out. Examples: us_states, currencies,
    status_codes, country_codes.

Critical rules — override heuristics when these apply:
  1. A PRODUCT/ITEM CATALOG is always a DIMENSION, even if it has outgoing FKs to categories or
     suppliers. Having outgoing FKs to lookup tables = snowflake pattern, not a fact.
  2. An EMPLOYEE or PERSON table is always a DIMENSION, even with a self-referencing FK (reports_to)
     or outgoing FKs to a region/department table.
  3. A true BRIDGE has almost no columns beyond its two FK columns. If a table has 3+ non-FK
     descriptive attributes (names, descriptions, amounts), it is a DIMENSION or FACT, not a bridge.
  4. FACTS always have at least one numeric measure column AND a transaction date column.
     "Header" tables (e.g. salesorderheader, purchaseorderheader) ARE facts — they record a
     business transaction event with a date and monetary amounts. Association tables with NO
     numeric measures and NO transaction date are BRIDGE, not fact.
  5. Reference/lookup tables (e.g. us_states, region) with no transactional data are REFERENCE.

Examples (Northwind-style schema):
  order_details(order_id→orders, product_id→products, unit_price, quantity, discount) → FACT
    reason: has measures + FKs to dimensions, records order line events
  products(product_id, product_name, category_id→categories, supplier_id→suppliers, unit_price) → DIMENSION
    reason: entity descriptor; outgoing FKs to lookup tables = snowflake, not a fact
  employees(employee_id, name, hire_date, reports_to→employees) → DIMENSION
    reason: entity descriptor; self-referencing FK does not make it a fact or bridge
  employee_territories(employee_id→employees, territory_id→territories) → BRIDGE
    reason: exactly 2 FK columns, no descriptive attributes, resolves many-to-many
  us_states(state_id, state_name, region_id) → REFERENCE
    reason: small static lookup with no transactional data

Additional examples (AdventureWorks-style schema):
  salesorderheader(salesorderid, customerid→customer, orderdate, subtotal, taxamt, totaldue) → FACT
    reason: records sales transaction event; has date + monetary amounts
  purchaseorderheader(purchaseorderid, vendorid→vendor, orderdate, totaldue, freight) → FACT
    reason: records procurement event; has date + monetary amounts
  shoppingcartitem(shoppingcartitemid, shoppingcartid, productid→product, quantity, datecreated) → FACT
    reason: records cart-add event; has date + quantity measure
  workorder(workorderid, productid→product, orderqty, scrappedqty, startdate, duedate) → FACT
    reason: records manufacturing event; has dates + quantity measures
  businessentityaddress(businessentityid→entity, addressid→address, addresstypeid→addresstype) → BRIDGE
    reason: pure association table; no numeric measures, no transaction date
  assigned_to(patient_id→patient, dept_id→department, date_assign, date_release, room_num) → FACT
    reason: has transaction dates (date_assign, date_release) + numeric measure (room_num); NOT a bridge despite 2 FKs
  works_for(doctor_id→doctor, dept_id→department) → BRIDGE
    reason: exactly 2 FK columns, no dates, no measures — pure M:M resolver
  enrollment(student_id→student, course_id→course, enroll_date, grade) → FACT
    reason: has event date + numeric measure (grade); association tables with dates/measures are facts

Output format: keep each `reasoning` to ≤8 words.
"""


_AGENT3_BATCH_SIZE = 20
# ~300 output tokens per table (fine-tuned model is more verbose than base) + buffer.
_AGENT3_MAX_TOKENS_PER_BATCH = _AGENT3_BATCH_SIZE * 300 + 512


def classify_tables(
    schema: Schema,
    context: PipelineContext,
    user_feedback: str | None = None,
) -> list[TableClassificationResult]:
    """Agent 3 — classify tables in batches, using FK heuristics as a prior.

    Each batch receives the FULL schema and heuristic context so cross-table
    relationships are visible, but is asked to output classifications for only
    ~20 tables at a time. This keeps output tokens predictable regardless of
    schema size and avoids the retry storm caused by truncated JSON.
    """
    # Separate partition children — they inherit the parent's role automatically
    # and must not be included in LLM batches (they'd inflate counts and confuse Agent 3).
    partition_child_names = {t.name for t in schema.tables if t.is_partition_child}
    regular_tables = [t for t in schema.tables if not t.is_partition_child]

    from schemalytics.models import Schema as _Schema
    heuristics = classify_by_fk_graph(_Schema(tables=regular_tables))

    from pydantic import BaseModel as _BaseModel

    class _ClassificationList(_BaseModel):
        classifications: list[TableClassificationResult]

    all_tables = regular_tables
    batches = [
        all_tables[i : i + _AGENT3_BATCH_SIZE]
        for i in range(0, len(all_tables), _AGENT3_BATCH_SIZE)
    ]
    n_batches = len(batches)

    all_classifications: list[TableClassificationResult] = []
    for idx, batch in enumerate(batches, start=1):
        batch_names = [t.name for t in batch]
        if n_batches > 1:
            console.print(f"  [dim][Agent 3] batch {idx}/{n_batches}: {batch_names}[/]")

        # Use schema format matching training data: col→ref_table inline.
        # For multi-batch, send only the batch tables so output length stays predictable.
        tables_for_batch = batch if n_batches > 1 else all_tables
        heuristics_for_batch = (
            [h for h in heuristics if h.table.name in {t.name for t in batch}]
            if n_batches > 1 else heuristics
        )
        business_ctx = (
            f"Business context: {context.industry} / {context.business_type}."
            + (f" Key metrics: {', '.join(context.metrics[:5])}." if context.metrics else "")
        )
        if user_feedback:
            business_ctx += f"\n\nUser correction / clarification: {user_feedback}"

        user_msg = (
            f"Database schema:\n{_agent3_schema_fmt(tables_for_batch)}\n\n"
            f"Heuristic pre-classifications:\n{_heuristic_summary(heuristics_for_batch)}\n\n"
            f"{business_ctx}"
        )

        result = llm.query_structured(
            system=_AGENT3_SYSTEM,
            user=user_msg,
            response_model=_ClassificationList,
            max_tokens=_AGENT3_MAX_TOKENS_PER_BATCH,
            model=_AGENT3_MODEL,
        )
        all_classifications.extend(result.classifications)

    # Normalize role to lowercase — LLMs sometimes return "Fact", "Dimension", etc.
    for c in all_classifications:
        c.role = c.role.lower()

    # Hard override: a table classified as bridge or reference that has BOTH a
    # business-event date column AND a numeric non-FK column is always a fact.
    # This corrects Agent 3's tendency to call junction-with-events tables like
    # assigned_to(patient_id, dept_id, date_assign, date_release, room_num) a bridge
    # even though rules 3 & 4 explicitly say otherwise.
    _tbl_lookup = {t.name: t for t in schema.tables}
    for c in all_classifications:
        if c.role in ("bridge", "reference"):
            tbl = _tbl_lookup.get(c.table_name)
            if tbl and _has_transaction_date(tbl):
                fk_cols = {fk.column for fk in tbl.foreign_keys}
                pk_cols = set(tbl.primary_key or [])
                _numeric_tokens = ("int", "num", "decimal", "float", "money", "real", "double")
                has_numeric = any(
                    col.name not in fk_cols
                    and col.name not in pk_cols
                    and any(tok in col.data_type.lower() for tok in _numeric_tokens)
                    for col in tbl.columns
                )
                if has_numeric:
                    old_role = c.role
                    c.role = "fact"
                    c.confidence = 3
                    c.reasoning = (
                        f"Hard override (was {old_role}): has business date + numeric measure"
                    )
                    c.needs_clarification = False

    # Auto-assign partition children the same role as their parent.
    classified_roles = {c.table_name: c.role for c in all_classifications}
    for t in schema.tables:
        if t.is_partition_child and t.name not in classified_roles:
            parent_role = classified_roles.get(t.partition_parent or "", "fact")
            all_classifications.append(TableClassificationResult(
                table_name=t.name,
                role=parent_role,
                confidence=3,
                reasoning=f"Partition child of {t.partition_parent} — inherits parent role",
                needs_clarification=False,
            ))

    return all_classifications


# ── Confidence Interaction Helper ──────────────────────────────────────────────

def _handle_confidence(
    result_description: str,
    confidence: int,
    reasoning: str,
    needs_clarification: bool,
    prompt_text: str,
) -> str | None:
    """Print result, ask user for input if confidence < 3. Returns user text or None."""
    if confidence == 3 and not needs_clarification:
        console.print(f"  [green]Detected:[/] {result_description}")
        console.print(f"  [dim]Reasoning: {reasoning}[/]")
        return None

    if confidence == 1:
        console.print(f"\n  [red]Low confidence:[/] {result_description}")
        console.print(f"  [dim]Reason: {reasoning}[/]")
    else:
        console.print(f"\n  [yellow]Moderate confidence:[/] {result_description}")
        console.print(f"  [dim]Reason: {reasoning}[/]")

    return input(f"  {prompt_text} (press Enter to accept): ").strip() or None


# ── Summary Gate ──────────────────────────────────────────────────────────────

_ROLE_KEYWORDS: dict[str, list[str]] = {
    "fact": ["fact", "facts"],
    "dimension": ["dimension", "dimensions", "dim"],
    "bridge": ["bridge", "bridges", "junction"],
    "reference": ["reference", "lookup"],
}


def _parse_role_overrides(correction: str, schema: Schema) -> dict[str, str]:
    """Extract explicit table→role overrides from a correction string.

    For each table name found in the correction, scan the surrounding text for
    role keywords. Returns a mapping of table_name → role for any tables where
    an unambiguous role is stated.
    """
    known_tables = {t.name.lower(): t.name for t in schema.tables}
    text = correction.lower()
    overrides: dict[str, str] = {}

    for table_lower, table_name in known_tables.items():
        if table_lower not in text:
            continue
        for role, keywords in _ROLE_KEYWORDS.items():
            if any(kw in text for kw in keywords):
                overrides[table_name] = role
                break

    return overrides


def _apply_overrides(
    classifications: list[TableClassificationResult],
    overrides: dict[str, str],
    correction: str,
) -> list[TableClassificationResult]:
    """Hard-apply explicit user overrides on top of existing classifications."""
    result = []
    for cls in classifications:
        if cls.table_name in overrides:
            result.append(
                TableClassificationResult(
                    table_name=cls.table_name,
                    role=overrides[cls.table_name],
                    confidence=3,
                    reasoning=f"User override: {correction}",
                    needs_clarification=False,
                )
            )
        else:
            result.append(cls)
    return result


def _print_summary_gate(context: PipelineContext) -> str | None:
    """Print the consolidated summary and collect user corrections. Returns correction or None."""
    facts = [c.table_name for c in context.table_classifications if c.role == "fact"]
    dims = [c.table_name for c in context.table_classifications if c.role == "dimension"]
    bridges = [c.table_name for c in context.table_classifications if c.role == "bridge"]
    refs = [c.table_name for c in context.table_classifications if c.role == "reference"]

    tbl = _RichTable(title="INFERRED CONTEXT — please review", show_header=True, header_style="bold")
    tbl.add_column("Category", style="bold cyan", min_width=14)
    tbl.add_column("Value")
    tbl.add_row("Industry", context.industry)
    tbl.add_row("Business type", context.business_type)
    tbl.add_row("Key metrics", ", ".join(context.metrics))
    tbl.add_row("Goals", ", ".join(context.goals))
    tbl.add_row("Grain", context.grain)
    tbl.add_row("Facts", ", ".join(facts) or "(none)")
    tbl.add_row("Dimensions", ", ".join(dims) or "(none)")
    tbl.add_row("Bridge", ", ".join(bridges) or "(none)")
    if refs:
        tbl.add_row("Reference", ", ".join(refs))

    console.print()
    console.print(tbl)
    console.print()

    correction = input("Anything wrong with the table roles? Enter corrections or press Enter to continue: ").strip()
    return correction or None


# ── Agent 4: Modeling Plan Generation ─────────────────────────────────────────

_AGENT4_SILVER_SYSTEM = """\
You are a senior data engineer generating the Silver layer of a medallion-architecture dbt plan.

Given a schema and pipeline context, produce a plan with:
  - bronze: list of ALL source table names (raw names only, no prefixes)
  - facts: Silver fact models (fct_<entity>)

NOTE: Dimension models are derived automatically from Agent 3 classifications — do NOT output them.

Rules:
  - Every source table must appear in bronze.
  - Fact names: fct_<entity>. source_table must match a table name in bronze.
  - STRICT: Only create fct_* from tables whose role is "fact". Never create a fact from a
    dimension, bridge, or reference table.
  - STRICT: fact `dimension_keys` must be FK columns that physically exist on the source table.
  - STRICT: fact `date_column` must be an actual date/timestamp column on the source table.
    If no date column exists on the table, look at its FK-referenced tables. If a parent table
    has a date/timestamp column (e.g. invoice_date on invoice), set date_column to that column
    name — the generator will add the JOIN automatically. Only use "" if no date is reachable
    via a single FK hop.
  - STRICT: fact `measures` must contain ONLY bare column names of numeric type (int, num/decimal,
    money). Column types are shown in the schema as :int, :num, :money. Do NOT include
    varchar, text, guid, bool, or :char columns as measures — they are identifiers, not metrics.
    Do NOT put SQL expressions in `measures`.
  - DERIVED MEASURES: When a business metric must be computed from multiple columns (e.g. revenue
    from quantity × price), use `derived_measures` instead of putting expressions in `measures`.
    Each entry has a `name` (SQL alias, e.g. "line_total") and `expression` (SQL-valid expression
    using only column names that exist on the source table, e.g. "orderqty * unitprice").
    Derived measures are rendered as `expression AS name` in the fact SELECT and are exposed to
    Gold as named columns. Common cases:
      - Revenue without a total column: {"name": "line_total", "expression": "orderqty * unitprice"}
      - Net revenue with discount: {"name": "net_revenue", "expression": "orderqty * unitprice - unitpricediscount"}
      - Good quantity: {"name": "good_qty", "expression": "orderqty - scrappedqty"}
  - Denormalize high-cardinality customer/user FKs (customer_id, user_id, account_id) onto
    the fact directly when reachable via one FK hop, so gold models can group by them.
  - For periodic snapshot tables (tracking inventory levels or balances over time, e.g.
    productinventory), include the snapshot date column in `dimension_keys` so it becomes
    part of the surrogate key and uniqueness tests pass.
  - Factless fact tables (no numeric measures, e.g. employeedepartmenthistory) are valid.
    Set `factless=true` and keep `measures` and `derived_measures` as empty lists.
"""

_AGENT4_GOLD_SYSTEM = """\
You are a senior data engineer generating Gold aggregation models for a dbt project.

Given the Silver plan (facts with their source tables and columns) and business context,
produce a list of Gold aggregate models (agg_<grain>_<metric>).

Rules:
  - `source_fact` must be a fact model name from the Silver plan (e.g. "fct_order_details").
  - `dimensions` must be FK column names that physically exist on the source fact table
    (e.g. "customer_id", "product_id") — never use model names like "dim_customer".
    Include the most analytically useful FK keys (e.g. product, customer, category) so gold
    models can be sliced by dimension without a join at query time.
  - CRITICAL: never include a fact's immediate parent entity key as a `dimension`. For example,
    on fct_order_items the parent entity is "order", so "order_id" must NOT be a dimension —
    it belongs as a COUNT_DISTINCT metric (e.g. name="order_count", column="order_id",
    aggregation="COUNT_DISTINCT"). Only use FK columns as dimensions when they point to true
    lookup dimensions (product, customer, category, status, etc.).
  - `date_column` must be an actual date/timestamp column on the source fact table.
  - `grain` must be one of: "daily", "monthly", "yearly", "weekly".
  - `aggregation` must be one of: SUM, COUNT, COUNT_DISTINCT, AVG, MIN, MAX.
  - `column` must be a BARE COLUMN NAME that exists in the Silver fact model — never an
    arithmetic expression. The only exception is the literal "*" for COUNT(*).
    Silver derived measures are available as named columns (listed in the fact summary as
    derived_measures=[name=expression, ...]). Reference their NAME only (e.g. "line_total"),
    not the underlying expression. Expressions in `column` are rejected at validation time
    and will cause the metric to be silently dropped. Never use a FK/dimension key as a metric.
  - CRITICAL: `column` is the raw physical column name from the fact's `measures` list, NOT a
    business metric name. If you want metric name="total_revenue" but the fact only has column
    "freight", write: name="total_revenue", column="freight". Never write column="total_revenue"
    unless "total_revenue" literally appears in the fact's measures or derived_measures list.
  - `date_column` must be a date/timestamp column physically present on the source fact model
    (including any FK-joined columns that appear in the fact's SELECT). Use "" if none exists.
  - Generate at least ONE gold model for EACH fact table in the Silver plan. Do not produce
    gold models only from the primary sales fact — every fact (purchasing, inventory, HR,
    manufacturing) needs at least one aggregate model.
  - Use CONSISTENT formulas across all gold models in the same project. If a measure is
    derived (e.g. from two source columns), use the same derivation everywhere — never mix
    formula variants for the same concept across models.
  - Use BUSINESS EVENT dates as `date_column` — the date the event occurred (e.g. orderdate,
    duedate, transactiondate). Do NOT use audit timestamps (modifieddate, updated_at, created_at)
    unless no business date exists on the fact.
  - Do NOT name a model agg_*_ytd with daily grain. YTD requires yearly grain. Use
    grain="monthly" for trend aggregations and let consumers apply YTD window functions.
  - Match metric domain to source fact domain: source customer/sales metrics from the sales
    fact, purchasing metrics from the purchasing fact, manufacturing from the workorder fact.
    The `measures` and `derived_measures` lists in each fact show exactly what columns are
    available. ONLY reference columns from those lists — do not invent column names.
  - CRITICAL: metric `name` must reflect the actual column being aggregated, NOT the business
    goal. If column=freight, name it total_freight or avg_freight_per_order — never
    total_revenue or customer_sales_volume. The column name is the ground truth; the business
    context is only for domain awareness.
"""


def _display_plan(plan: ModelingPlan) -> None:
    """Print ModelingPlan in human-readable format."""
    console.print()

    # Bronze panel — simple bullet list
    bronze_lines = "\n".join(f"  • {t}" for t in plan.bronze) or "  (none)"
    console.print(Panel(
        bronze_lines,
        title=f"[bold]Bronze[/] ({len(plan.bronze)} tables)",
        border_style="dim",
    ))

    # Silver panel — dims and facts as labeled items
    silver_lines = []
    for d in plan.dimensions:
        silver_lines.append(
            f"  [cyan]dim[/] {d.name}  "
            f"[dim]SCD{d.scd_type}  source={d.source_table}  grain={d.grain}[/]"
        )
    for f in plan.facts:
        silver_lines.append(
            f"  [yellow]fct[/] {f.name}  "
            f"[dim]source={f.source_table}  grain={f.grain}  "
            f"date={f.date_column}  measures={f.measures}[/]"
        )
    console.print(Panel(
        "\n".join(silver_lines) or "  (none)",
        title=f"[bold]Silver[/] ({len(plan.dimensions)} dims, {len(plan.facts)} facts)",
        border_style="yellow",
    ))

    # Gold panel — labeled items with grain and measures
    gold_lines = []
    for g in plan.gold:
        metric_names = [m.name for m in g.metrics]
        gold_lines.append(
            f"  [gold1]{g.name}[/]  "
            f"[dim][{g.grain}]  source={g.source_fact}  metrics={metric_names}[/]"
        )
    console.print(Panel(
        "\n".join(gold_lines) or "  (none)",
        title=f"[bold]Gold[/] ({len(plan.gold)} aggregates)",
        border_style="gold1",
    ))


def _is_sql_expression(s: str) -> bool:
    """Return True if s looks like a SQL expression rather than a bare column name."""
    return any(ch in s for ch in ("*", "+", "-", "/", " ", "(", ")"))


_SQL_KEYWORDS = {
    "sum", "count", "avg", "min", "max", "distinct", "as", "and", "or", "not",
    "null", "true", "false", "case", "when", "then", "else", "end", "over",
    "partition", "by", "order", "rows", "unbounded", "preceding", "following",
    "current", "row", "interval",
}


def _extract_expression_col_refs(expr: str) -> set[str]:
    """Return bare column name tokens from a SQL expression, excluding SQL keywords."""
    tokens = _re.findall(r'\b[a-zA-Z_]\w*\b', expr)
    return {t.lower() for t in tokens if t.lower() not in _SQL_KEYWORDS}


_FLOAT_TYPES = {
    "numeric", "decimal", "float", "float4", "float8",
    "double precision", "real", "money", "smallmoney",
}
_INT_TYPES = {
    "integer", "int", "int2", "int4", "int8",
    "bigint", "smallint", "tinyint",
}
_MEASURE_KEYWORDS = {
    "qty", "quantity", "amount", "count", "total", "price", "cost", "value",
    "rate", "pct", "revenue", "profit", "margin", "weight", "score",
    "hrs", "hours", "days", "units", "size", "volume", "balance",
}


def _col_is_measure(col) -> bool:
    """Return True if a column is likely a numeric measure (not an identifier/code).

    Float/decimal/money types are always measures.
    Integer types are measures only when the column name contains a measure-indicating
    keyword — this excludes status codes, bin numbers, type flags, etc.
    """
    dt = col.data_type.lower().split("(")[0].strip()
    if dt in _FLOAT_TYPES:
        return True
    if dt in _INT_TYPES:
        return any(kw in col.name.lower() for kw in _MEASURE_KEYWORDS)
    return False


def _schema_summary_agent4a(schema: Schema, context: PipelineContext) -> str:
    """Schema summary for Agent 4a input.

    Dimensions: one compact line each (name + FK cols only) — columns are
    auto-filled from schema by _sanitize_plan so the LLM doesn't need them.
    Facts + others: full column listing with FK annotations.
    Partition children: skipped — parent entry includes a partition note.
    """
    dim_names = {c.table_name for c in context.table_classifications if c.role == "dimension"}

    # Build parent → [child names] map for partition annotation
    partition_children_of: dict[str, list[str]] = {}
    for t in schema.tables:
        if t.is_partition_child and t.partition_parent:
            partition_children_of.setdefault(t.partition_parent, []).append(t.name)

    lines = []
    for t in schema.tables:
        if t.is_partition_child:
            continue  # covered by parent entry below
        fks = ", ".join(f"{fk.column}→{fk.references_table}" for fk in t.foreign_keys)
        if t.name in dim_names:
            line = f"  {t.name} [dim]"
            if fks:
                line += f": fks=[{fks}]"
        else:
            cols = ", ".join(c.name for c in t.columns[:15])
            line = f"  {t.name}: columns=[{cols}]"
            if fks:
                line += f", fks=[{fks}]"
        children = partition_children_of.get(t.name)
        if children:
            line += f" [partition parent — {len(children)} partitions; model fact from this table only]"
        lines.append(line)
    return "\n".join(lines)


def _numeric_cols_hint(schema: Schema, context: PipelineContext) -> str:
    """One-liner per fact table listing only numeric measure-eligible columns.

    Far more compact than annotating every column — lists ~3-6 numeric
    columns per fact rather than all columns of every table.
    """
    fact_names = {c.table_name for c in context.table_classifications if c.role == "fact"}
    lines = []
    for t in schema.tables:
        if t.name not in fact_names:
            continue
        numeric = [c.name for c in t.columns if _col_is_measure(c)]
        if numeric:
            lines.append(f"  {t.name}: {', '.join(numeric)}")
    if not lines:
        return ""
    return "Numeric columns eligible as measures (use ONLY these in `measures`):\n" + "\n".join(lines)


# ── SCD Type Heuristic ────────────────────────────────────────────────────────

# Tables whose names contain these patterns are almost always static reference
# data — SCD Type 2 on them is unnecessary overhead.
_SCD1_NAME_PATTERNS = {
    "country", "city", "language", "category", "type", "status", "code",
    "region", "zone", "territory", "currency", "unit", "state", "province",
    "lookup", "reference",
}

# Tables whose names match these patterns are business entities that genuinely
# change over time and warrant full SCD Type 2 history.
_SCD2_NAME_PATTERNS = {
    "customer", "client", "employee", "staff", "user", "account",
    "vendor", "supplier", "contact", "person", "partner", "member",
}


def _infer_scd_type(table: Table) -> int:
    """Determine the appropriate SCD type from table name and column count.

    Returns 2 for business entities (customers, staff, etc.) and 1 for
    reference/lookup tables or small tables without a compelling change story.
    Defaults to Type 1 to avoid generating unnecessary snapshots.
    """
    name = table.name.lower()
    if any(p in name for p in _SCD2_NAME_PATTERNS):
        return 2
    if any(p in name for p in _SCD1_NAME_PATTERNS):
        return 1
    if len(table.columns) <= 6:
        return 1
    return 1  # conservative default — avoid snapshot overhead unless justified


# ── FK Chain Traversal ────────────────────────────────────────────────────────

# Column names that represent audit/ownership provenance (who created or last
# touched a row) rather than a meaningful business dimension FK.  These columns
# frequently point at a staff/user table, which would cause the generator to
# denormalise "who created this coupon" or "who approved this record" onto every
# fact that touches that entity — not analytically useful and semantically wrong.
_INDIRECT_KEY_COL_DENYLIST: frozenset[str] = frozenset({
    "created_by", "updated_by", "modified_by", "last_updated_by",
    "created_by_id", "updated_by_id", "modified_by_id",
    "deleted_by", "deleted_by_id",
    "approved_by", "approved_by_id",
    "reviewed_by", "reviewed_by_id",
    "assigned_to", "assigned_to_id",
    "owned_by", "owned_by_id",
})


def _compute_indirect_keys(
    fact: FactPlan,
    schema_tbl_map: dict[str, Table],
    role_map: dict[str, str],
) -> list[IndirectKey]:
    """Find dimension keys reachable from a fact via 2-hop FK traversal.

    Traverses each FK on the source fact table. If the referenced table is NOT
    a dimension (e.g. an inventory/junction table), checks its FKs for dimension
    references. Those second-hop FK columns are returned as IndirectKey objects
    so the generator can emit LEFT JOINs and include them in the fact SELECT.

    Only adds keys not already present in fact.dimension_keys (no duplicates).
    """
    source_tbl = schema_tbl_map.get(fact.source_table)
    if not source_tbl:
        return []

    direct_key_cols = set(fact.dimension_keys)
    seen: set[str] = set(direct_key_cols)
    indirect: list[IndirectKey] = []

    for fk in source_tbl.foreign_keys:
        # Traverse ALL FK targets regardless of their role — the intermediate table
        # may itself be a dimension (e.g. inventory) but still carry transitive FK
        # columns worth denormalising (film_id, store_id). The `seen` set prevents
        # adding columns already present in fact.dimension_keys.
        ref_tbl = schema_tbl_map.get(fk.references_table)
        if not ref_tbl:
            continue
        for hop2_fk in ref_tbl.foreign_keys:
            if role_map.get(hop2_fk.references_table) != "dimension":
                continue
            if hop2_fk.column in seen:
                continue  # already present or already added
            # Skip audit/provenance FK columns — they represent who touched a row,
            # not a meaningful dimensional relationship (e.g. coupon.created_by,
            # order.updated_by).  Denormalising them into facts produces noise.
            if hop2_fk.column.lower() in _INDIRECT_KEY_COL_DENYLIST:
                continue
            seen.add(hop2_fk.column)
            indirect.append(IndirectKey(
                column_alias=hop2_fk.column,
                join_table=fk.references_table,
                join_on=fk.column,
                join_pk=fk.references_column,
                source_col=hop2_fk.column,
            ))

    return indirect


def _sanitize_plan(plan: ModelingPlan, schema: Schema) -> ModelingPlan:
    """Strip hallucinated column names from the plan; only keep columns that exist in the source table."""
    col_map: dict[str, set[str]] = {t.name: {c.name for c in t.columns} for t in schema.tables}
    table_obj_map: dict[str, Table] = {t.name: t for t in schema.tables}

    # Sanitize dimension column lists; auto-fill from schema when LLM left them empty.
    sanitized_dims = []
    for dim in plan.dimensions:
        source_tbl_obj = table_obj_map.get(dim.source_table)
        cols = col_map.get(dim.source_table, set())
        valid_cols = [c for c in dim.columns if not cols or c in cols]
        if not valid_cols and cols:
            # LLM returned [] (as instructed) — populate all real columns in schema order
            for t in schema.tables:
                if t.name == dim.source_table:
                    valid_cols = [c.name for c in t.columns]
                    break
        # Dedup while preserving schema order — guards against duplicate column names
        # returned by the LLM or appearing in the schema extraction result.
        seen: set[str] = set()
        deduped = [c for c in (valid_cols or dim.columns) if not (c in seen or seen.add(c))]  # type: ignore[func-returns-value]
        # Override LLM's SCD type with deterministic heuristic — the fine-tuned
        # model tends to return Type 2 for everything; the heuristic applies
        # Type 2 only to genuine business entities (customers, staff, etc.).
        scd_type = _infer_scd_type(source_tbl_obj) if source_tbl_obj else dim.scd_type
        sanitized_dims.append(
            DimensionPlan(name=dim.name, source_table=dim.source_table,
                          scd_type=scd_type, grain=dim.grain,
                          columns=deduped)
        )

    # Sanitize fact column lists.
    sanitized_facts = []
    for fact in plan.facts:
        source_tbl = next((t for t in schema.tables if t.name == fact.source_table), None)
        cols = col_map.get(fact.source_table, set())
        if not cols:
            sanitized_facts.append(fact)
            continue

        # ── 1. date column ────────────────────────────────────────────────────
        date_col = fact.date_column if fact.date_column in cols else ""
        if not date_col and source_tbl:
            for c in source_tbl.columns:
                if c.data_type.lower() in _DATE_COLUMN_TYPES:
                    date_col = c.name
                    break

        # ── 1b. extra business event dates ───────────────────────────────────
        # Scan the source table for additional non-audit timestamp/date columns
        # beyond the primary date_col.  These are genuine business event dates
        # (e.g. order_approved_at, order_delivered_customer_date) that should
        # appear in the fact SELECT so analysts can do delivery-time analytics
        # without rejoining the source.  Audit timestamps (created_at, updated_at
        # etc.) are excluded — they are system metadata, not event signals.
        extra_dates: list[str] = []
        if source_tbl:
            for _c in source_tbl.columns:
                if _c.data_type.lower() not in _DATE_COLUMN_TYPES:
                    continue
                if _c.name.lower() in _AUDIT_TIMESTAMP_NAMES:
                    continue
                if _c.name == date_col:
                    continue  # already the primary date
                extra_dates.append(_c.name)

        # ── 2. dimension_keys — must be FK columns only ───────────────────────
        # Non-FK numeric columns in dimension_keys are misclassifications by Agent 4.
        # Keep them but move them to measures so they're not described as FKs in YAML.
        actual_fk_cols = {fk.column for fk in source_tbl.foreign_keys} if source_tbl else set()
        raw_dim_keys = [k for k in fact.dimension_keys if k in cols]
        dim_keys: list[str] = []
        reclassified_to_measures: list[str] = []
        for k in raw_dim_keys:
            if actual_fk_cols and k not in actual_fk_cols and k != date_col:
                src_col = next((c for c in source_tbl.columns if c.name == k), None) if source_tbl else None
                if src_col and _col_is_measure(src_col):
                    reclassified_to_measures.append(k)
                    continue
            dim_keys.append(k)

        # ── 3. measures — validate column names; enforce numeric type ─────────
        # Bare column names must (a) exist in the source table AND (b) be a
        # numeric type (_col_is_measure). SQL expressions are kept as-is only
        # when they contain no bare column references — but the preferred path
        # for expressions is now derived_measures (see step 3b below).
        # Prepend any numeric columns reclassified from dimension_keys.
        col_obj_map = {c.name: c for c in source_tbl.columns} if source_tbl else {}
        measures = [
            m for m in fact.measures
            if _is_sql_expression(m)
            or (m in cols and _col_is_measure(col_obj_map[m]))
        ]
        measures = reclassified_to_measures + [m for m in measures if m not in reclassified_to_measures]

        # ── 3b. derived_measures — validate expression column refs exist ───────
        valid_derived: list[DerivedMeasure] = []
        seen_exprs: set[str] = set()
        for dm in fact.derived_measures:
            refs = _extract_expression_col_refs(dm.expression)
            if not refs.issubset(cols):
                continue  # drop — expression references non-existent columns
            normalized = dm.expression.replace(" ", "").lower()
            if normalized in seen_exprs:
                continue  # drop — duplicate expression (different name, same formula)
            seen_exprs.add(normalized)
            valid_derived.append(dm)

        # ── 4. auto-fill measures when LLM returned none ──────────────────────
        # Uses name+type heuristic (_col_is_measure) instead of type alone,
        # so identifier integers (status codes, bin numbers, type flags) are excluded.
        is_factless = fact.factless
        if not measures and not is_factless and source_tbl:
            fk_cols_set = {fk.column for fk in source_tbl.foreign_keys}
            pk_cols_set = set(source_tbl.primary_key or [])
            exclude = fk_cols_set | pk_cols_set | ({date_col} if date_col else set())
            measures = [
                c.name for c in source_tbl.columns
                if _col_is_measure(c) and c.name not in exclude
            ]
            if not measures:
                # Still no numeric columns — this fact is genuinely factless.
                is_factless = True

        sanitized_facts.append(
            FactPlan(name=fact.name, source_table=fact.source_table, grain=fact.grain,
                     dimension_keys=dim_keys or fact.dimension_keys,
                     measures=measures,
                     derived_measures=valid_derived,
                     # Never fall back to fact.date_column if sanitization cleared it — that column
                     # was cleared because it doesn't exist on the source table. An empty date_col
                     # here means the generator's Fix-C will locate a date via FK-joined parent.
                     date_column=date_col,
                     factless=is_factless,
                     indirect_keys=fact.indirect_keys,  # pass through — computed outside sanitize
                     extra_date_columns=extra_dates)
        )

    # Build the fact model column set — what each fact model actually SELECTs.
    # Gold metrics must reference columns from this set, NOT from the raw source table.
    # This is the correct contract: Gold reads from Silver fact models, not raw sources.
    # Derived measure names are included because they are rendered as named aliases
    # in the fact SELECT (e.g. "orderqty * unitprice AS line_total") and are therefore
    # available as columns to downstream Gold models.
    fact_model_cols: dict[str, set[str]] = {
        f.name: (
            set(f.dimension_keys)
            | set(f.measures)
            | {dm.name for dm in f.derived_measures}
            | ({f.date_column} if f.date_column else set())
            | {ik.column_alias for ik in f.indirect_keys}
            | set(f.extra_date_columns)
        )
        for f in sanitized_facts
    }

    # Sanitize gold models: validate source_fact exists, then validate all column references
    # against the fact MODEL's columns (not the raw source table).
    valid_fact_names = {f.name for f in sanitized_facts}
    sanitized_gold = []
    for gold in plan.gold:
        if gold.source_fact not in valid_fact_names:
            continue  # drop — source_fact doesn't exist or has wrong domain
        model_cols = fact_model_cols.get(gold.source_fact, set())
        dims = [d for d in gold.dimensions if not model_cols or d in model_cols]
        # Do NOT fall back if the date_column doesn't exist in the fact model —
        # a hallucinated column would produce invalid SQL.
        date_col = gold.date_column if (not model_cols or gold.date_column in model_cols) else ""
        # Validate each metric column against fact model columns.
        # STRICT CONTRACT: Gold metric columns must be bare names declared in
        # Silver (either as a measure or a derived_measure alias) or the special
        # literal "*" (for COUNT(*)).  Arithmetic expressions are NOT allowed —
        # any computed value must be declared as a DerivedMeasure in Silver and
        # referenced by its alias. This enforces full lineage traceability and
        # prevents Gold from inventing measures with no Silver provenance.
        valid_metrics = []
        for m in gold.metrics:
            if m.column == "*":
                valid_metrics.append(m)
            elif not model_cols:
                # No schema info available — pass through (defensive)
                valid_metrics.append(m)
            elif _is_sql_expression(m.column):
                pass  # expressions rejected — must be declared as derived_measure in Silver
            elif m.column in model_cols:
                valid_metrics.append(m)
            # else: bare column not in fact model — silently drop
        if not valid_metrics:
            # Fallback: if the model has exactly one numeric measure available, remap all
            # metrics to it. This handles the common case where the fine-tuned model uses
            # a semantic name (e.g. "total_revenue") instead of the raw column (e.g. "freight").
            source_fact_plan = next((f for f in sanitized_facts if f.name == gold.source_fact), None)
            fact_measures = (
                [m for m in source_fact_plan.measures]
                + [dm.name for dm in source_fact_plan.derived_measures]
            ) if source_fact_plan else []
            numeric_measures = [c for c in fact_measures if c in model_cols]
            if len(numeric_measures) == 1:
                fallback_col = numeric_measures[0]
                for m in gold.metrics:
                    if not _is_sql_expression(m.column) and m.column != "*":
                        valid_metrics.append(
                            MetricDefinition(name=m.name, aggregation=m.aggregation,
                                             column=fallback_col, description=m.description)
                        )
            if not valid_metrics:
                continue  # no usable metrics — drop the whole model
        # RC5: enforce _ytd models have yearly grain (daily _ytd is a logical contradiction)
        fixed_grain = (
            "yearly"
            if gold.name.endswith("_ytd") and gold.grain in ("daily", "day", "weekly")
            else gold.grain
        )
        sanitized_gold.append(
            GoldPlan(name=gold.name, source_fact=gold.source_fact, grain=fixed_grain,
                     dimensions=dims, metrics=valid_metrics,
                     date_column=date_col,
                     description=gold.description)
        )

    return ModelingPlan(bronze=plan.bronze, dimensions=sanitized_dims,
                        facts=sanitized_facts, gold=sanitized_gold)


def generate_modeling_plan(schema: Schema, context: PipelineContext) -> ModelingPlan:
    """Agent 4 — two focused LLM calls: Silver (bronze+dims+facts) then Gold aggregates."""
    from pydantic import BaseModel as _BM

    # Partition children inherit parent's role — exclude them from table_roles so
    # Agent 4a doesn't generate individual fct_payment_p2022_01, fct_payment_p2022_02, etc.
    # They still appear in bronze (all_tables) so staging models are generated.
    _partition_child_names = {t.name for t in schema.tables if t.is_partition_child}
    table_roles = "\n".join(
        f"  {c.table_name}: {c.role}"
        for c in context.table_classifications
        if c.table_name not in _partition_child_names
    )
    all_tables = [t.name for t in schema.tables if not t.is_partition_child]
    context_block = (
        f"  Industry: {context.industry} / {context.business_type}\n"
        f"  Metrics:  {', '.join(context.metrics)}\n"
        f"  Goals:    {', '.join(context.goals)}\n"
        f"  Grain:    {context.grain}"
    )

    # ── Call A: Silver (bronze + facts only) ──────────────────────────────────
    # Pipeline-managed fields (indirect_keys, extra_date_columns) are NEVER
    # exposed to the LLM — they are populated by _sanitize_plan and
    # _compute_indirect_keys after the LLM call. Exposing them would bloat the
    # instructor JSON schema, trigger fine-tuned model repetition loops, and
    # cause retry accumulation to overflow num_ctx on large schemas.
    # Dimensions are auto-built from Agent 3 classifications (no LLM needed).
    class _LLMFactPlan(_BM):
        name: str
        source_table: str
        grain: str
        dimension_keys: list[str]
        measures: list[str]
        derived_measures: list[DerivedMeasure] = []
        date_column: str
        factless: bool = False

    class _SilverPlan(_BM):
        bronze: list[str]
        facts: list[_LLMFactPlan]

    n_bronze = len(all_tables)
    n_dims = sum(1 for c in context.table_classifications
                 if c.role == "dimension" and c.table_name not in _partition_child_names)
    n_facts = sum(1 for c in context.table_classifications
                  if c.role == "fact" and c.table_name not in _partition_child_names)
    # No dims in LLM output — token budget = bronze list + facts only.
    silver_max_tokens = min(4096, n_bronze * 5 + n_facts * 400 + 512)
    console.print(f"  [dim][Agent 4a] tables={n_bronze}  dims={n_dims}  facts={n_facts}  "
                  f"max_tokens={silver_max_tokens}[/]")

    numeric_hint = _numeric_cols_hint(schema, context)
    silver_user = (
        f"Database schema:\n{_schema_summary_agent4a(schema, context)}\n\n"
        f"All source tables (all must appear in bronze): {all_tables}\n\n"
        f"Pipeline context:\n{context_block}\n\n"
        f"Table roles (from Agent 3):\n{table_roles}"
        + (f"\n\n{numeric_hint}" if numeric_hint else "")
    )
    silver = llm.query_structured(
        system=_AGENT4_SILVER_SYSTEM,
        user=silver_user,
        response_model=_SilverPlan,
        max_tokens=silver_max_tokens,
        model=_AGENT4A_MODEL,
    )
    console.print(f"  [green]✓[/] 4a Silver done  [dim][{_ts()}][/]")

    # ── Auto-build DimensionPlan objects from Agent 3 classifications ──────────
    # "dimension" and "reference" roles → DimensionPlan; scd_type via heuristic.
    # Bridges go to bronze only (no Silver model).
    _schema_tbl_map_early = {t.name: t for t in schema.tables}
    _dim_role_set = {"dimension", "reference"}
    auto_dims: list[DimensionPlan] = []
    for _c in context.table_classifications:
        if _c.table_name in _partition_child_names:
            continue
        if _c.role not in _dim_role_set:
            continue
        _tbl = _schema_tbl_map_early.get(_c.table_name)
        _scd = _infer_scd_type(_tbl) if _tbl else 1
        auto_dims.append(DimensionPlan(
            name=f"dim_{_c.table_name}",
            source_table=_c.table_name,
            scd_type=_scd,
            grain=_c.table_name,
            columns=[],
        ))

    # Promote _LLMFactPlan → FactPlan (pipeline fields default to empty).
    llm_facts = [
        FactPlan(
            name=f.name,
            source_table=f.source_table,
            grain=f.grain,
            dimension_keys=f.dimension_keys,
            measures=f.measures,
            derived_measures=f.derived_measures,
            date_column=f.date_column,
            factless=f.factless,
        )
        for f in silver.facts
    ]

    # ── Sanitize Silver first so Gold sees accurate, validated measures ────────
    # This is the pipeline contract: downstream agents only receive what upstream
    # agents have provably declared and what the schema can validate.
    interim_plan = ModelingPlan(
        bronze=silver.bronze,
        dimensions=auto_dims,
        facts=llm_facts,
        gold=[],
    )
    sanitized_silver = _sanitize_plan(interim_plan, schema)

    # ── Compute 2-hop FK denormalization (indirect keys) ─────────────────────
    # Done AFTER sanitization so dimension_keys are already clean.
    # Traverses each non-dimension FK on every fact to find dimension keys
    # reachable via an intermediate table (e.g. rental→inventory→film).
    _role_map = {c.table_name: c.role for c in context.table_classifications}
    _schema_tbl_map = {t.name: t for t in schema.tables}
    _enriched_facts = []
    for _fact in sanitized_silver.facts:
        _iks = _compute_indirect_keys(_fact, _schema_tbl_map, _role_map)
        _enriched_facts.append(_fact.model_copy(update={"indirect_keys": _iks}) if _iks else _fact)
    sanitized_silver = ModelingPlan(
        bronze=sanitized_silver.bronze,
        dimensions=sanitized_silver.dimensions,
        facts=_enriched_facts,
        gold=[],
    )

    # ── Call B: Gold aggregates (given sanitized silver facts as context) ─────
    # Budget: ~1000 tokens per fact (3-4 gold models with dimension lists each) + buffer.
    # Capped at 6000 to stay within num_ctx=12288 alongside the prompt (~500 token input).
    n_gold_facts = len(sanitized_silver.facts)
    gold_max_tokens = min(6000, n_gold_facts * 1000 + 512)
    console.print(f"  [dim][Agent 4b] facts={n_gold_facts}  max_tokens={gold_max_tokens}  [{_ts()}][/]")
    class _GoldContainer(_BM):
        gold: list[GoldPlan]

    def _fact_summary_line(f: FactPlan) -> str:
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

    fact_summary = "\n".join(_fact_summary_line(f) for f in sanitized_silver.facts)
    fact_names = [f.name for f in sanitized_silver.facts]
    gold_user = (
        f"Industry: {context.industry} / {context.business_type}\n\n"
        f"Silver facts ({len(fact_names)} total — you MUST produce at least one Gold model for EACH):\n"
        f"{fact_summary}\n\n"
        f"Required facts to cover: {fact_names}\n"
        "Use ONLY the measures and derived_measures columns listed for each fact. "
        "Metric name must reflect the column name, not the business goal."
    )
    gold_result = llm.query_structured(
        system=_AGENT4_GOLD_SYSTEM,
        user=gold_user,
        response_model=_GoldContainer,
        max_tokens=gold_max_tokens,
        model=_AGENT4B_MODEL,
    )
    console.print(f"  [green]✓[/] 4b Gold done  [dim][{_ts()}][/]")

    # Combine sanitized silver with raw gold, then sanitize gold against the
    # already-clean silver (fact_model_cols reflects sanitized facts).
    plan = ModelingPlan(
        bronze=sanitized_silver.bronze,
        dimensions=sanitized_silver.dimensions,
        facts=sanitized_silver.facts,
        gold=gold_result.gold,
    )
    return _sanitize_plan(plan, schema)


# ── Agent 5: Refinement Loop ───────────────────────────────────────────────────

_AGENT5_SYSTEM = """\
You are a senior data engineer refining a dbt ModelingPlan based on user feedback.

Apply the user's feedback precisely and return the COMPLETE updated plan.
When the user says "change X to Y": remove X and add Y.
When the user says "delete X": remove X from the plan entirely.
When the user says "add X": add X to the appropriate section.

Rules:
  - Return the full plan — not a diff or partial update.
  - Every source_table referenced in dimensions/facts must appear in bronze.
  - Naming conventions: dim_<entity>, fct_<entity>, agg_<grain>_<metric>.
  - Gold metric aggregation must be one of: SUM, COUNT, COUNT_DISTINCT, AVG, MIN, MAX.
  - Gold grain must be one of: "daily", "monthly", "yearly", "weekly".
"""


def refine_modeling_plan(
    plan: ModelingPlan,
    feedback: str,
    schema: Schema,
    context: PipelineContext,
) -> ModelingPlan:
    """Agent 5 — apply user feedback to produce a revised ModelingPlan."""
    # Schema omitted: column validation is done by _sanitize_plan after this call.
    # indent=None (compact JSON) saves ~150-200 tokens vs indent=2.
    plan_json = plan.model_dump_json()
    # chars / 3 is conservative (usual ratio is /4) — gives headroom for the
    # revised plan being slightly larger than the current one.
    agent5_max_tokens = min(6000, len(plan_json) // 3 + 1024)
    console.print(f"  [dim][Agent 5] plan_json={len(plan_json):,} chars  max_tokens={agent5_max_tokens}[/]")

    user_msg = (
        f"Current plan (JSON):\n{plan_json}\n\n"
        f"Business context:\n"
        f"  Industry: {context.industry} / {context.business_type}\n"
        f"  Metrics:  {', '.join(context.metrics)}\n"
        f"  Goals:    {', '.join(context.goals)}\n\n"
        f"User feedback: {feedback}"
    )

    return llm.query_structured(
        system=_AGENT5_SYSTEM,
        user=user_msg,
        response_model=ModelingPlan,
        max_tokens=agent5_max_tokens,
    )


# ── Plan Diff Display ──────────────────────────────────────────────────────────

def _show_plan_diff(old: ModelingPlan, new: ModelingPlan) -> None:
    """Print a diff of what changed between two ModelingPlan versions."""
    changes: list[str] = []

    old_bronze = set(old.bronze)
    new_bronze = set(new.bronze)
    for t in sorted(new_bronze - old_bronze):
        changes.append(f"  + Added bronze: {t}")
    for t in sorted(old_bronze - new_bronze):
        changes.append(f"  - Removed bronze: {t}")

    old_dims = {d.name: d for d in old.dimensions}
    new_dims = {d.name: d for d in new.dimensions}
    for name in sorted(set(new_dims) - set(old_dims)):
        changes.append(f"  + Added {name}")
    for name in sorted(set(old_dims) - set(new_dims)):
        changes.append(f"  - Removed {name}")
    for name in sorted(set(old_dims) & set(new_dims)):
        if old_dims[name] != new_dims[name]:
            changes.append(f"  ~ Changed {name}")

    old_facts = {f.name: f for f in old.facts}
    new_facts = {f.name: f for f in new.facts}
    for name in sorted(set(new_facts) - set(old_facts)):
        changes.append(f"  + Added {name}")
    for name in sorted(set(old_facts) - set(new_facts)):
        changes.append(f"  - Removed {name}")
    for name in sorted(set(old_facts) & set(new_facts)):
        if old_facts[name] != new_facts[name]:
            changes.append(f"  ~ Changed {name}")

    old_gold = {g.name: g for g in old.gold}
    new_gold = {g.name: g for g in new.gold}
    for name in sorted(set(new_gold) - set(old_gold)):
        changes.append(f"  + Added {name}")
    for name in sorted(set(old_gold) - set(new_gold)):
        changes.append(f"  - Removed {name}")
    for name in sorted(set(old_gold) & set(new_gold)):
        if old_gold[name] != new_gold[name]:
            changes.append(f"  ~ Changed {name}")

    console.print("\n[bold]Changes:[/]")
    if changes:
        for c in changes:
            if c.startswith("  + "):
                console.print(f"[green]{c}[/]")
            elif c.startswith("  - "):
                console.print(f"[red]{c}[/]")
            elif c.startswith("  ~ "):
                console.print(f"[yellow]{c}[/]")
            else:
                console.print(c)
    else:
        console.print("  [dim](no structural changes detected)[/]")


# ── Agent 6: Semantic Layer ────────────────────────────────────────────────────

_AGENT6_SYSTEM = """\
You are a senior analytics engineer generating a dbt-native semantic layer definition.

Given a finalized modeling plan (Silver facts + dimensions + Gold aggregates) and business context,
produce a complete semantic layer in dbt format.

Rules:
- semantic_models: create ONLY one per Silver FACT table. The count must equal the number of Silver facts
  listed. Do NOT create semantic_models for Gold aggregates, dimensions, or bridge tables.
- entities: include the fact's primary surrogate key as type="primary", and each FK dimension key
  (e.g. customer_id, employee_id) as type="foreign". FK keys go ONLY in entities, never in dimensions.
- dimensions: ONLY date/timestamp columns go here, as type="time" with appropriate time_granularity.
  Do NOT put FK keys or categorical columns in dimensions.
- measures: one measure per numeric column in the fact. Use "sum" for amounts/quantities, "count_distinct"
  for IDs, "avg" for rates/ratios.
- metrics: you will receive an explicit list of required metrics. Output ALL of them inside the
  metrics[] array of the appropriate semantic_model. CRITICAL: metrics go INSIDE semantic_model.metrics[],
  NOT as separate top-level entries in the semantic_models list. Every item in semantic_models must
  have a "model" field — if it lacks a "model" field, it is invalid.
  Use type="simple" for direct aggregations. type_params must be {"measure": "<measure_name>"} where
  <measure_name> matches a measure defined in that same semantic_model.
  Example metric JSON: {"name": "total_revenue", "label": "Total Revenue",
    "description": "Sum of revenue across all orders", "type": "simple",
    "type_params": {"measure": "total_revenue"}}
- All names must be snake_case. Labels should be human-readable title case.
- Keep descriptions concise (under 12 words).
"""

_AGENT6_MAX_TOKENS = 5000


def generate_semantic_layer(plan: ModelingPlan, context: PipelineContext) -> SemanticLayer:
    """Agent 6 — generate dbt-native semantic layer from the finalized modeling plan."""
    facts_block = "\n".join(
        f"  {f.name}: grain={f.grain}  date={f.date_column}  "
        f"keys={f.dimension_keys}  measures={f.measures + [dm.name for dm in f.derived_measures]}"
        for f in plan.facts
    )
    gold_block = "\n".join(
        f"  {g.name}: source={g.source_fact}  grain={g.grain}  "
        f"metrics={[m.name + '(' + m.aggregation + ':' + m.column + ')' for m in g.metrics]}"
        for g in plan.gold
    )
    # Build explicit list of required metrics so the model doesn't have to infer them.
    required_metrics_lines = []
    seen_metric_names: set[str] = set()
    for g in plan.gold:
        for m in g.metrics:
            if m.name not in seen_metric_names:
                seen_metric_names.add(m.name)
                required_metrics_lines.append(
                    f"  - name={m.name}  aggregation={m.aggregation}  column={m.column}"
                    f"  (from semantic_model for {g.source_fact})"
                )
    required_metrics_block = "\n".join(required_metrics_lines) if required_metrics_lines else "  (none)"
    user_msg = (
        f"Business context: {context.industry} / {context.business_type}\n\n"
        f"Silver facts:\n{facts_block}\n\n"
        f"Gold models:\n{gold_block}\n\n"
        f"Required semantic_models ({len(plan.facts)} total, one per Silver fact): "
        f"{', '.join(f.name for f in plan.facts)}\n\n"
        f"Required metrics ({len(seen_metric_names)} total — output ALL of them):\n"
        f"{required_metrics_block}\n\n"
        f"Generate the semantic layer. Create exactly {len(plan.facts)} semantic_model(s) — "
        "one per Silver fact listed above. For each required metric, place it inside the metrics[] "
        "array of the semantic_model for its source fact. Do NOT add metrics as separate entries "
        "in semantic_models — only semantic_model objects with a 'model' field are valid there."
    )
    return llm.query_structured(
        system=_AGENT6_SYSTEM,
        user=user_msg,
        response_model=SemanticLayer,
        max_tokens=_AGENT6_MAX_TOKENS,
    )


def _check_finetuned_models() -> None:
    """Check that fine-tuned Ollama models are pulled; warn and prompt if not.

    Skipped when SCHEMALYTICS_LLM_PROVIDER != 'ollama'.
    Only checks model names that start with 'nichr0/' (i.e. the fine-tuned defaults,
    not user overrides pointing at local models).
    """
    if llm.get_provider() != "ollama":
        return

    # Re-read env vars here rather than using the module-level globals so that
    # overrides pointing at non-nichr0/ models (e.g. a local fine-tune) skip the
    # availability check for that agent — no ollama pull warning needed.
    agent3  = os.environ.get("SCHEMALYTICS_AGENT3_MODEL",  "nichr0/schemalytics-classification-agent")
    agent4a = os.environ.get("SCHEMALYTICS_AGENT4A_MODEL", "nichr0/schemalytics-silver-agent")
    agent4b = os.environ.get("SCHEMALYTICS_AGENT4B_MODEL", "nichr0/schemalytics-gold-agent")

    candidates = [
        ("Agent 3 (classification)", agent3),
        ("Agent 4a (silver plan)",   agent4a),
        ("Agent 4b (gold plan)",     agent4b),
    ]
    to_check = [(label, name) for label, name in candidates if name.startswith("nichr0/")]
    if not to_check:
        return

    try:
        result = subprocess.run(
            ["ollama", "list"], capture_output=True, text=True, timeout=10
        )
        if result.returncode != 0:
            console.print("[yellow]Warning:[/] 'ollama list' returned an error. Skipping model availability check.")
            return
        available = result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        console.print(f"[yellow]Warning:[/] could not run 'ollama list' ({exc}). Skipping model availability check.")
        return

    # Normalise: strip :latest tag so "nichr0/foo" matches "nichr0/foo:latest"
    available_names = {
        line.split()[0].removesuffix(":latest")
        for line in available.splitlines()
        if line.strip() and not line.startswith("NAME")
    }
    missing = [(label, name) for label, name in to_check if name not in available_names]
    if not missing:
        return

    console.print()
    for label, name in missing:
        console.print(f"[yellow]Warning:[/] fine-tuned model '[bold]{name}[/]' is not pulled.")
        console.print(f"  [dim]→ Run: ollama pull {name}[/]")
        console.print(f"  [dim]→ {label} will use {llm.OLLAMA_DEFAULT_MODEL} instead (quality may be lower).[/]")
        console.print()

    answer = input("Continue anyway? [y/N] ").strip().lower()
    if answer != "y":
        raise SystemExit(1)

    # Patch module-level constants for this run so agent calls pick up the fallback.
    global _AGENT3_MODEL, _AGENT4A_MODEL, _AGENT4B_MODEL
    for _, name in missing:
        if name == agent3:
            _AGENT3_MODEL = llm.OLLAMA_DEFAULT_MODEL
        if name == agent4a:
            _AGENT4A_MODEL = llm.OLLAMA_DEFAULT_MODEL
        if name == agent4b:
            _AGENT4B_MODEL = llm.OLLAMA_DEFAULT_MODEL


# ── Main Pipeline Orchestrator ─────────────────────────────────────────────────

def run_pipeline(schema: Schema) -> tuple[ModelingPlan, PipelineContext] | None:
    """Run the agent pipeline. Returns (ModelingPlan, PipelineContext) or None if cancelled."""
    _check_finetuned_models()

    # ── Agent 1: Industry Inference ────────────────────────────────────────────
    with console.status("[bold blue]Agent 1 — Inferring industry and domain...[/]"):
        industry_result = infer_industry(schema)
    console.print(f"[green]✓[/] Agent 1 done  [dim][{_ts()}][/]")

    agent1_desc = f"{industry_result.industry} ({industry_result.business_type})"
    correction = _handle_confidence(
        result_description=agent1_desc,
        confidence=industry_result.confidence,
        reasoning=industry_result.reasoning,
        needs_clarification=industry_result.needs_clarification,
        prompt_text="Describe your business (or press Enter to accept the inference above)",
    )
    if correction:
        with console.status("[bold blue]Re-running Agent 1...[/]"):
            industry_result = infer_industry(schema, user_feedback=correction)
        console.print(f"[green]✓[/] Updated: {industry_result.industry} / {industry_result.business_type}  [dim][{_ts()}][/]")

    # ── Agent 2: Metrics + Goals ───────────────────────────────────────────────
    console.print()
    with console.status("[bold blue]Agent 2 — Suggesting metrics and goals...[/]"):
        metrics_result = suggest_metrics(schema, industry_result)
    console.print(f"[green]✓[/] Agent 2 done  [dim][{_ts()}][/]")

    agent2_desc = (
        f"metrics={metrics_result.metrics[:3]}... "
        f"grain={metrics_result.suggested_grain}"
    )
    correction = _handle_confidence(
        result_description=agent2_desc,
        confidence=metrics_result.confidence,
        reasoning=metrics_result.reasoning,
        needs_clarification=metrics_result.needs_clarification,
        prompt_text=(
            metrics_result.clarification_question
            if metrics_result.clarification_question
            else "Confirm or describe the metrics and goals you care about"
        ),
    )
    if correction:
        with console.status("[bold blue]Re-running Agent 2...[/]"):
            metrics_result = suggest_metrics(schema, industry_result, user_feedback=correction)
        console.print(f"[green]✓[/] Updated metrics: {metrics_result.metrics[:4]}  [dim][{_ts()}][/]")

    # ── Build partial context for Agent 3 ─────────────────────────────────────
    partial_context = PipelineContext(
        industry=industry_result.industry,
        business_type=industry_result.business_type,
        metrics=metrics_result.metrics,
        goals=metrics_result.goals,
        grain=metrics_result.suggested_grain,
        table_classifications=[],
    )

    # ── Agent 3: Table Classification ─────────────────────────────────────────
    console.print()
    with console.status("[bold blue]Agent 3 — Classifying tables...[/]"):
        classifications = classify_tables(schema, partial_context)
    console.print(f"[green]✓[/] Agent 3 done  [dim][{_ts()}][/]")

    # Flag only low-confidence tables
    low_conf = [c for c in classifications if c.confidence < 3]
    if low_conf:
        console.print("\n  [yellow]The following tables have uncertain classifications:[/]")
        for c in low_conf:
            console.print(
                f"    [yellow]{c.table_name}[/]: {c.role} "
                f"[dim](confidence={c.confidence}) — {c.reasoning}[/]"
            )
        correction = input(
            "  Correct any table roles in plain English (or press Enter to accept): "
        ).strip()
        if correction:
            with console.status("[bold blue]Re-running Agent 3...[/]"):
                classifications = classify_tables(schema, partial_context, user_feedback=correction)
            console.print(f"[green]✓[/] Agent 3 done  [dim][{_ts()}][/]")
    else:
        console.print("  [green]All table classifications are high-confidence.[/]")

    # ── Assemble full PipelineContext ──────────────────────────────────────────
    context = PipelineContext(
        industry=industry_result.industry,
        business_type=industry_result.business_type,
        metrics=metrics_result.metrics,
        goals=metrics_result.goals,
        grain=metrics_result.suggested_grain,
        table_classifications=classifications,
    )

    # ── Summary Gate ──────────────────────────────────────────────────────────
    correction = _print_summary_gate(context)
    if correction:
        overrides = _parse_role_overrides(correction, schema)
        if overrides:
            # Explicit table→role correction: apply as hard overrides without re-running
            # Agent 3. Re-running destabilizes other correct classifications because the
            # LLM may swap roles for unrelated tables when given new context.
            console.print(f"  [cyan]Applying overrides:[/] { {t: r for t, r in overrides.items()} }")
            classifications = _apply_overrides(
                context.table_classifications, overrides, correction
            )
        else:
            # Vague/contextual correction (no explicit table names): re-run Agent 3.
            with console.status(f"[bold blue]Applying corrections — re-running Agent 3...[/]"):
                classifications = classify_tables(schema, context, user_feedback=correction)
            console.print(f"[green]✓[/] Agent 3 done  [dim][{_ts()}][/]")
        context = PipelineContext(
            industry=context.industry,
            business_type=context.business_type,
            metrics=context.metrics,
            goals=context.goals,
            grain=context.grain,
            table_classifications=classifications,
        )

    # ── Agent 4: Generate Modeling Plan ───────────────────────────────────────
    console.print()
    with console.status("[bold blue]Agent 4 — Generating modeling plan (Silver + Gold)...[/]"):
        plan = generate_modeling_plan(schema, context)
    console.print(f"[green]✓[/] Agent 4 done  [dim][{_ts()}][/]")
    _display_plan(plan)

    # ── Refinement loop (Agent 5) ──────────────────────────────────────────────
    while True:
        console.print(
            "\n[dim]Type natural language feedback to refine the plan, "
            "or press Enter to approve.[/]"
        )
        feedback = input("Feedback: ").strip()

        if not feedback:
            console.print(f"\n[green]Plan approved.[/] Proceeding to generation...  [dim][{_ts()}][/]")
            return plan, context

        if feedback.lower() in {"cancel", "abort", "quit", "exit", "reject"}:
            console.print("\n[yellow]Cancelled.[/]")
            return None

        old_plan = plan
        with console.status("[bold blue]Agent 5 — Applying feedback...[/]"):
            plan = refine_modeling_plan(plan, feedback, schema, context)
        console.print(f"[green]✓[/] Agent 5 done  [dim][{_ts()}][/]")
        _show_plan_diff(old_plan, plan)
        _display_plan(plan)
