#!/usr/bin/env python3
"""
Generate synthetic SQL schemas for missing domains using Claude,
then parse them into the extracted JSON format used by label_silver.py.

Output: finetune/extracted_new/<db_id>.json

Run from repo root:
    python finetune/scripts/generate_synthetic_schemas.py
"""

import json
import os
import sys
import time
from pathlib import Path

import anthropic

ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(ROOT))

from finetune.scripts.download_and_extract import parse_sql

OUTPUT_DIR = Path("finetune/extracted_new")
OUTPUT_DIR.mkdir(exist_ok=True)

# ---------------------------------------------------------------------------
# Domains to generate
# ---------------------------------------------------------------------------

DOMAINS = [
    {
        "db_id": "banking",
        "description": "Retail banking system",
        "guidance": """
Include tables for: customers, accounts (checking/savings/credit), transactions,
loans, loan_payments, cards (debit/credit), branches, employees, transfers,
beneficiaries, standing_orders, account_types, interest_rates.
~18 tables. Heavy FK relationships between accounts, transactions, loans.
""",
    },
    {
        "db_id": "hotel",
        "description": "Hotel management and reservation system",
        "guidance": """
Include tables for: hotels, room_types, rooms, guests, reservations,
reservation_rooms, check_ins, check_outs, invoices, invoice_items,
amenities, room_amenities, staff, departments, housekeeping_tasks,
services, service_requests, loyalty_programs, loyalty_accounts.
~18 tables. FKs linking reservations to guests, rooms, invoices.
""",
    },
    {
        "db_id": "telecom",
        "description": "Telecommunications billing and subscriber management",
        "guidance": """
Include tables for: subscribers, accounts, plans, plan_features,
subscriptions, devices, sim_cards, call_records, sms_records,
data_usage, invoices, invoice_items, payments, towers, coverage_areas,
service_tickets, promotions, subscriber_promotions.
~18 tables. FKs linking subscribers to subscriptions, plans, invoices.
""",
    },
    {
        "db_id": "pharmacy",
        "description": "Pharmacy and prescription management system",
        "guidance": """
Include tables for: patients, doctors, pharmacists, drugs, drug_categories,
manufacturers, suppliers, inventory, prescriptions, prescription_items,
dispensing_records, drug_interactions, allergies, patient_allergies,
insurance_providers, insurance_claims, refills, dosage_forms.
~18 tables. FKs linking prescriptions to patients, doctors, drugs.
""",
    },
    {
        "db_id": "crm_sales",
        "description": "Full CRM and sales pipeline management",
        "guidance": """
Include tables for: companies, contacts, leads, opportunities,
opportunity_stages, activities, activity_types, tasks, notes,
products, product_categories, quotes, quote_items, orders, order_items,
campaigns, campaign_members, territories, sales_reps, sales_targets.
~20 tables. FKs linking opportunities to contacts, companies, quotes.
""",
    },
    {
        "db_id": "fleet_management",
        "description": "Fleet and vehicle management system",
        "guidance": """
Include tables for: vehicles, vehicle_types, vehicle_makes, vehicle_models,
drivers, driver_licenses, driver_assignments, trips, trip_legs,
fuel_logs, maintenance_records, maintenance_types, inspections,
accidents, insurance_policies, depots, routes, customers, rentals.
~18 tables. FKs linking vehicles to drivers, trips, maintenance.
""",
    },
    {
        "db_id": "warehouse_wms",
        "description": "Warehouse management system",
        "guidance": """
Include tables for: warehouses, zones, locations, products, product_variants,
suppliers, purchase_orders, purchase_order_items, receipts, receipt_items,
inventory, inventory_movements, sales_orders, sales_order_items,
shipments, shipment_items, carriers, picking_tasks, packing_tasks,
quality_checks, returns.
~20 tables. FKs linking inventory movements to locations, products, orders.
""",
    },
    {
        "db_id": "project_management",
        "description": "Project management and issue tracking system",
        "guidance": """
Include tables for: organizations, projects, project_members, milestones,
sprints, issues, issue_types, issue_statuses, issue_priorities,
comments, attachments, labels, issue_labels, time_logs, workflows,
workflow_transitions, notifications, users, teams, team_members,
repositories, commits, pull_requests.
~22 tables. FKs linking issues to projects, sprints, users, milestones.
""",
    },
    {
        "db_id": "manufacturing",
        "description": "Manufacturing ERP - production and inventory",
        "guidance": """
Include tables for: products, product_categories, raw_materials,
bill_of_materials, bom_items, suppliers, purchase_orders, purchase_order_items,
warehouses, stock_locations, inventory, production_orders, production_order_items,
work_centers, operations, routing, quality_checks, defects,
customers, sales_orders, sales_order_items, shipments, cost_centers.
~22 tables. FKs linking production_orders to bom, work_centers, inventory.
""",
    },
    {
        "db_id": "legal_case_mgmt",
        "description": "Legal case and court management system",
        "guidance": """
Include tables for: courts, judges, attorneys, law_firms, clients,
cases, case_types, case_statuses, parties, party_roles,
hearings, hearing_outcomes, documents, document_types,
charges, verdicts, sentences, appeals, evidence, evidence_types,
billing_records, invoices, payments, statutes.
~22 tables. FKs linking cases to courts, judges, parties, hearings.
""",
    },
    {
        "db_id": "elearning_platform",
        "description": "Online learning platform / LMS",
        "guidance": """
Include tables for: users, instructors, courses, course_categories,
modules, lessons, lesson_content, enrollments, progress,
quizzes, questions, answer_options, quiz_attempts, quiz_answers,
assignments, submissions, grades, certificates, forums, forum_posts,
payments, subscriptions, discount_codes.
~22 tables. FKs linking enrollments to users, courses, progress.
""",
    },
    {
        "db_id": "real_estate",
        "description": "Real estate property management system",
        "guidance": """
Include tables for: properties, property_types, property_features,
property_images, owners, tenants, agents, agencies, listings,
viewings, offers, contracts, leases, lease_payments,
maintenance_requests, maintenance_tasks, inspections,
mortgages, valuations, neighborhoods, amenities, property_amenities.
~22 tables. FKs linking leases to properties, tenants; listings to agents.
""",
    },
]

# ---------------------------------------------------------------------------
# Prompt
# ---------------------------------------------------------------------------

SYSTEM = """\
You are a senior database architect. Generate realistic PostgreSQL CREATE TABLE
statements for the described domain. Follow these rules:

1. Use snake_case for all table and column names
2. Every table must have a primary key (id SERIAL PRIMARY KEY or similar)
3. Include proper FOREIGN KEY constraints with REFERENCES clauses
4. Include realistic columns with appropriate data types
5. Add NOT NULL constraints where logically required
6. Include created_at TIMESTAMP and updated_at TIMESTAMP on main entities
7. Include sensible CHECK constraints where appropriate (e.g. status IN (...))
8. Do NOT include INSERT statements, indexes, or triggers — schema only
9. Output ONLY valid SQL CREATE TABLE statements, nothing else
10. Aim for the target table count specified

Output format: raw SQL only, starting with the first CREATE TABLE statement."""


def generate_schema(client: anthropic.Anthropic, domain: dict) -> str:
    prompt = (
        f"Domain: {domain['description']}\n\n"
        f"Requirements:\n{domain['guidance'].strip()}\n\n"
        f"Generate complete PostgreSQL CREATE TABLE statements for this domain."
    )
    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4096,
        system=SYSTEM,
        messages=[{"role": "user", "content": prompt}],
    )
    return next((b.text for b in response.content if hasattr(b, "text")), "")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERROR: ANTHROPIC_API_KEY not set")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    print(f"Generating {len(DOMAINS)} synthetic schemas -> {OUTPUT_DIR}\n")

    results = {"ok": [], "few_tables": [], "failed": []}

    for i, domain in enumerate(DOMAINS):
        db_id = domain["db_id"]
        out_path = OUTPUT_DIR / f"{db_id}.json"

        if out_path.exists():
            tables = json.loads(out_path.read_text())["tables"]
            print(f"  [{i+1}/{len(DOMAINS)}] SKIP {db_id} (already done, {len(tables)} tables)")
            results["ok"].append(db_id)
            continue

        print(f"  [{i+1}/{len(DOMAINS)}] Generating {db_id} ({domain['description']})...")

        try:
            sql = generate_schema(client, domain)
            if not sql.strip():
                raise ValueError("Empty response")

            tables = parse_sql(sql)
            if len(tables) < 10:
                print(f"    WARNING: only {len(tables)} tables parsed — saving anyway")

            fk_count = sum(len(t["foreign_keys"]) for t in tables)
            schema = {"tables": tables}
            out_path.write_text(json.dumps(schema, indent=2, ensure_ascii=False), encoding="utf-8")
            print(f"    OK — {len(tables)} tables, {fk_count} FKs")
            results["ok"].append(db_id)

        except Exception as e:
            print(f"    ERR: {e}")
            results["failed"].append(db_id)

        time.sleep(0.5)

    print(f"\n--- Summary ---")
    print(f"  OK:      {len(results['ok'])} schemas")
    print(f"  Failed:  {results['failed']}")
    print(f"\nNext: run label_silver.py to label these schemas")


if __name__ == "__main__":
    main()
