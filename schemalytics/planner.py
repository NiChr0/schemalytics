"""Agentic pipeline: five focused agents for schema-to-dbt planning."""
from __future__ import annotations

import os
import subprocess
from datetime import datetime

import re as _re

from schemalytics import llm
from schemalytics.models import (
    DerivedMeasure,
    DimensionPlan,
    FactPlan,
    GoldPlan,
    IndustryInference,
    MetricDefinition,
    MetricsSuggestion,
    ModelingPlan,
    PipelineContext,
    Schema,
    SemanticLayer,
    Table,
    TableClassificationResult,
)


def _ts() -> str:
    """Current wall-clock time as HH:MM:SS for inline progress stamps."""
    return datetime.now().strftime('%H:%M:%S')


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


def _agent3_schema_fmt(tables: list) -> str:
    """Schema format matching Agent 3 training data: col→ref_table inline for FK columns."""
    lines = []
    for t in tables:
        fk_map = {fk.column: fk.references_table for fk in t.foreign_keys}
        col_parts = []
        for c in t.columns[:12]:
            col_parts.append(f"{c.name}→{fk_map[c.name]}" if c.name in fk_map else c.name)
        lines.append(f"  {t.name}({', '.join(col_parts)})")
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
    heuristics = classify_by_fk_graph(schema)

    from pydantic import BaseModel as _BaseModel

    class _ClassificationList(_BaseModel):
        classifications: list[TableClassificationResult]

    all_tables = schema.tables
    batches = [
        all_tables[i : i + _AGENT3_BATCH_SIZE]
        for i in range(0, len(all_tables), _AGENT3_BATCH_SIZE)
    ]
    n_batches = len(batches)

    all_classifications: list[TableClassificationResult] = []
    for idx, batch in enumerate(batches, start=1):
        batch_names = [t.name for t in batch]
        if n_batches > 1:
            print(f"  [Agent 3] batch {idx}/{n_batches}: {batch_names}")

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
        print(f"  Detected: {result_description}")
        print(f"  Reasoning: {reasoning}")
        return None

    if confidence == 1:
        print(f"\n  Low confidence: {result_description}")
        print(f"  Reason: {reasoning}")
    else:
        print(f"\n  Moderate confidence: {result_description}")
        print(f"  Reason: {reasoning}")

    return input(f"  {prompt_text} (press Enter to accept): ").strip() or None


# ── Summary Gate ──────────────────────────────────────────────────────────────

def _print_summary_gate(context: PipelineContext) -> str | None:
    """Print the consolidated summary and collect user corrections. Returns correction or None."""
    facts = [c.table_name for c in context.table_classifications if c.role == "fact"]
    dims = [c.table_name for c in context.table_classifications if c.role == "dimension"]
    bridges = [c.table_name for c in context.table_classifications if c.role == "bridge"]
    refs = [c.table_name for c in context.table_classifications if c.role == "reference"]

    print("\n" + "━" * 64)
    print("INFERRED CONTEXT — please review")
    print("━" * 64)
    print(f"Industry:     {context.industry} ({context.business_type})")
    print(f"Key metrics:  {', '.join(context.metrics)}")
    print(f"Goals:        {', '.join(context.goals)}")
    print(f"Grain:        {context.grain}")
    print()
    print("Table roles:")
    print(f"  facts:       {', '.join(facts) or '(none)'}")
    print(f"  dimensions:  {', '.join(dims) or '(none)'}")
    print(f"  bridge:      {', '.join(bridges) or '(none)'}")
    if refs:
        print(f"  reference:   {', '.join(refs)}")
    print()
    correction = input("Anything wrong with the table roles? Enter corrections or press Enter to continue: ").strip()
    print("━" * 64)

    return correction or None


# ── Agent 4: Modeling Plan Generation ─────────────────────────────────────────

_AGENT4_SILVER_SYSTEM = """\
You are a senior data engineer generating the Silver layer of a medallion-architecture dbt plan.

Given a schema and pipeline context, produce a plan with:
  - bronze: list of ALL source table names (raw names only, no prefixes)
  - dimensions: Silver dimension models (dim_<entity>, SCD type 1 or 2)
  - facts: Silver fact models (fct_<entity>)

Rules:
  - Every source table must appear in bronze.
  - source_table in dimensions/facts must match a table name in bronze.
  - Dimension names: dim_<entity>. Fact names: fct_<entity>.
  - Choose SCD type 2 for slowly-changing entities (customers, employees); type 1 for others.
  - STRICT: Only create fct_* from tables whose role is "fact". Never create a fact from a
    dimension, bridge, or reference table.
  - STRICT: `columns` in every DimensionPlan MUST be an empty list []. Do not enumerate columns.
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
  - `dimensions` must ALWAYS be an empty list []. Gold models aggregate to the time grain
    only — no FK dimension breakdowns. Dimensional slicing is done at query time by consumers.
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
  - Use a CONSISTENT revenue formula across all gold models. When a discount column exists
    (e.g. unitpricediscount), always deduct it: (orderqty * unitprice) - unitpricediscount.
    Never mix discount and non-discount formulas across models in the same project.
  - Average Order Value (AOV) must be at ORDER level, not line-item level. Use SUM for
    total_revenue and COUNT_DISTINCT for order_count; do not use AVG on individual line items.
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
    print("\n" + "=" * 64)
    print("MODELING PLAN")
    print("=" * 64)

    print(f"\nBronze ({len(plan.bronze)} tables):")
    for t in plan.bronze:
        print(f"  {t}")

    print(f"\nSilver Dimensions ({len(plan.dimensions)}):")
    for d in plan.dimensions:
        print(f"  {d.name}  [SCD{d.scd_type}]  source={d.source_table}  grain={d.grain}")

    print(f"\nSilver Facts ({len(plan.facts)}):")
    for f in plan.facts:
        print(
            f"  {f.name}  source={f.source_table}  grain={f.grain}  "
            f"date={f.date_column}  measures={f.measures}"
        )

    print(f"\nGold ({len(plan.gold)}):")
    for g in plan.gold:
        metric_names = [m.name for m in g.metrics]
        print(f"  {g.name}  [{g.grain}]  source={g.source_fact}  metrics={metric_names}")

    print("=" * 64)


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


def _sanitize_plan(plan: ModelingPlan, schema: Schema) -> ModelingPlan:
    """Strip hallucinated column names from the plan; only keep columns that exist in the source table."""
    col_map: dict[str, set[str]] = {t.name: {c.name for c in t.columns} for t in schema.tables}

    # Sanitize dimension column lists; auto-fill from schema when LLM left them empty.
    sanitized_dims = []
    for dim in plan.dimensions:
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
        sanitized_dims.append(
            DimensionPlan(name=dim.name, source_table=dim.source_table,
                          scd_type=dim.scd_type, grain=dim.grain,
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
        for dm in fact.derived_measures:
            refs = _extract_expression_col_refs(dm.expression)
            if refs.issubset(cols):
                valid_derived.append(dm)
            # else: drop — expression references non-existent columns

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
                     date_column=date_col or fact.date_column,
                     factless=is_factless)
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

    table_roles = "\n".join(
        f"  {c.table_name}: {c.role}"
        for c in context.table_classifications
    )
    all_tables = [t.name for t in schema.tables]
    context_block = (
        f"  Industry: {context.industry} / {context.business_type}\n"
        f"  Metrics:  {', '.join(context.metrics)}\n"
        f"  Goals:    {', '.join(context.goals)}\n"
        f"  Grain:    {context.grain}"
    )

    # ── Call A: Silver (bronze + dimensions + facts) ───────────────────────────
    class _SilverPlan(_BM):
        bronze: list[str]
        dimensions: list[DimensionPlan]
        facts: list[FactPlan]

    n_bronze = len(schema.tables)
    n_dims = sum(1 for c in context.table_classifications if c.role == "dimension")
    n_facts = sum(1 for c in context.table_classifications if c.role == "fact")
    silver_max_tokens = min(6000, n_bronze * 10 + n_dims * 100 + n_facts * 150 + 512)
    print(f"  [Agent 4a] tables={n_bronze}  dims={n_dims}  facts={n_facts}  "
          f"max_tokens={silver_max_tokens}")

    numeric_hint = _numeric_cols_hint(schema, context)
    silver_user = (
        f"Database schema:\n{_schema_summary(schema)}\n\n"
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
    print(f"  4a Silver done  [{_ts()}]")

    # ── Sanitize Silver first so Gold sees accurate, validated measures ────────
    # This is the pipeline contract: downstream agents only receive what upstream
    # agents have provably declared and what the schema can validate.
    interim_plan = ModelingPlan(
        bronze=silver.bronze,
        dimensions=silver.dimensions,
        facts=silver.facts,
        gold=[],
    )
    sanitized_silver = _sanitize_plan(interim_plan, schema)

    # ── Call B: Gold aggregates (given sanitized silver facts as context) ─────
    # Budget: ~500 tokens per fact (one gold model each) + small buffer.
    # Capped at 6000 to stay within num_ctx=12288 alongside the prompt.
    n_gold_facts = len(sanitized_silver.facts)
    gold_max_tokens = min(6000, n_gold_facts * 500 + 512)
    print(f"  4b Gold starting...  facts={n_gold_facts}  max_tokens={gold_max_tokens}  [{_ts()}]")
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
    print(f"  4b Gold done  [{_ts()}]")

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
    print(f"  [Agent 5] plan_json={len(plan_json):,} chars  max_tokens={agent5_max_tokens}")

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

    print("\nChanges:")
    if changes:
        for c in changes:
            print(c)
    else:
        print("  (no structural changes detected)")


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
- metrics: you will receive an explicit list of required metrics. Output ALL of them — the metrics array
  must never be empty. Use type="simple" for direct aggregations.
  type_params must be {"measure": "<measure_name>"} where <measure_name> matches a measure in a semantic_model.
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
        "one per Silver fact listed above. Output every required metric in the metrics list."
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
            print("Warning: 'ollama list' returned an error. Skipping model availability check.")
            return
        available = result.stdout
    except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
        print(f"Warning: could not run 'ollama list' ({exc}). Skipping model availability check.")
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

    print()
    for label, name in missing:
        print(f"Warning: fine-tuned model '{name}' is not pulled.")
        print(f"  → Run: ollama pull {name}")
        print(f"  → {label} will use {llm.OLLAMA_DEFAULT_MODEL} instead (quality may be lower).")
        print()

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

def run_pipeline(schema: Schema) -> tuple[ModelingPlan, PipelineContext, SemanticLayer] | None:
    """Run the full six-agent pipeline. Returns (ModelingPlan, PipelineContext, SemanticLayer) or None if cancelled."""
    _check_finetuned_models()

    # ── Agent 1: Industry Inference ────────────────────────────────────────────
    print(f"\nAgent 1 — Inferring industry and domain...  [{_ts()}]")
    industry_result = infer_industry(schema)
    print(f"  Done  [{_ts()}]")

    agent1_desc = f"{industry_result.industry} ({industry_result.business_type})"
    correction = _handle_confidence(
        result_description=agent1_desc,
        confidence=industry_result.confidence,
        reasoning=industry_result.reasoning,
        needs_clarification=industry_result.needs_clarification,
        prompt_text="Describe your business (or press Enter to accept the inference above)",
    )
    if correction:
        print(f"  Re-running Agent 1...  [{_ts()}]")
        industry_result = infer_industry(schema, user_feedback=correction)
        print(f"  Updated: {industry_result.industry} / {industry_result.business_type}  [{_ts()}]")

    # ── Agent 2: Metrics + Goals ───────────────────────────────────────────────
    print(f"\nAgent 2 — Suggesting metrics and goals...  [{_ts()}]")
    metrics_result = suggest_metrics(schema, industry_result)
    print(f"  Done  [{_ts()}]")

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
        print(f"  Re-running Agent 2...  [{_ts()}]")
        metrics_result = suggest_metrics(schema, industry_result, user_feedback=correction)
        print(f"  Updated metrics: {metrics_result.metrics[:4]}  [{_ts()}]")

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
    print(f"\nAgent 3 — Classifying tables...  [{_ts()}]")
    classifications = classify_tables(schema, partial_context)
    print(f"  Done  [{_ts()}]")

    # Flag only low-confidence tables
    low_conf = [c for c in classifications if c.confidence < 3]
    if low_conf:
        print("\n  The following tables have uncertain classifications:")
        for c in low_conf:
            print(
                f"    {c.table_name}: {c.role} (confidence={c.confidence}) — {c.reasoning}"
            )
        correction = input(
            "  Correct any table roles in plain English (or press Enter to accept): "
        ).strip()
        if correction:
            print(f"  Re-running Agent 3...  [{_ts()}]")
            classifications = classify_tables(schema, partial_context, user_feedback=correction)
            print(f"  Done  [{_ts()}]")
    else:
        print("  All table classifications are high-confidence.")

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
        # Summary gate corrections are almost always about table roles — only re-run Agent 3.
        # Agents 1 and 2 have their own earlier confirmation steps.
        print(f"  Applying corrections — re-running Agent 3...  [{_ts()}]")
        classifications = classify_tables(schema, context, user_feedback=correction)
        context = PipelineContext(
            industry=context.industry,
            business_type=context.business_type,
            metrics=context.metrics,
            goals=context.goals,
            grain=context.grain,
            table_classifications=classifications,
        )

    # ── Agent 4: Generate Modeling Plan ───────────────────────────────────────
    print(f"\nAgent 4 — Generating modeling plan (Silver + Gold)...  [{_ts()}]")
    plan = generate_modeling_plan(schema, context)
    _display_plan(plan)

    # ── Refinement loop (Agent 5) ──────────────────────────────────────────────
    while True:
        print(
            "\nType natural language feedback to refine the plan, "
            "or press Enter to approve."
        )
        feedback = input("Feedback: ").strip()

        if not feedback:
            print(f"\nPlan approved. Proceeding to generation...  [{_ts()}]")
            print(f"\nAgent 6 — Generating semantic layer...  [{_ts()}]")
            semantic_layer = generate_semantic_layer(plan, context)
            print(f"  Done — {len(semantic_layer.semantic_models)} semantic models, "
                  f"{len(semantic_layer.metrics)} metrics  [{_ts()}]")
            return plan, context, semantic_layer

        if feedback.lower() in {"cancel", "abort", "quit", "exit", "reject"}:
            print("\nCancelled.")
            return None

        print(f"  Agent 5 — Applying feedback...  [{_ts()}]")
        old_plan = plan
        plan = refine_modeling_plan(plan, feedback, schema, context)
        print(f"  Done  [{_ts()}]")
        _show_plan_diff(old_plan, plan)
        _display_plan(plan)
