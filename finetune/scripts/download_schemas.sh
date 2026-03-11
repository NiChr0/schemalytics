#!/bin/bash
# Download public domain SQL schema dumps for fine-tuning data collection.
# Run from repo root: bash finetune/scripts/download_schemas.sh

set -e
SCHEMAS_DIR="finetune/schemas"
mkdir -p "$SCHEMAS_DIR"

download() {
    local name="$1"
    local url="$2"
    local dest="$SCHEMAS_DIR/${name}.sql"
    echo "Downloading ${name}..."
    if curl -fsSL "$url" -o "$dest"; then
        echo "  OK: $dest"
    else
        echo "  SKIP: ${name} (failed to download from $url)"
        rm -f "$dest"
    fi
}

# --- Confirmed public schema dumps ---
download sakila    "https://raw.githubusercontent.com/jOOQ/sakila/main/postgres-sakila-db/postgres-sakila-schema.sql"
download employees "https://raw.githubusercontent.com/vrajmohan/pgsql-sample-db/master/employee/employee.sql"
download pagila    "https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-schema.sql"
download hospital  "https://raw.githubusercontent.com/rohitraut3366/hospital-management-system-database/master/hospital.sql"
download ecommerce "https://raw.githubusercontent.com/paulius-mongirdas/ecommerce-database/main/database.sql"
download university "https://raw.githubusercontent.com/YohanObadia/SQL-exercises/master/university_db.sql"

# --- Additional schemas for diversity ---
download chinook   "https://raw.githubusercontent.com/lerocha/chinook-database/master/ChinookDatabase/DataSources/Chinook_PostgreSql.sql"
download dvdrental "https://raw.githubusercontent.com/devrimgunduz/pagila/master/pagila-data.sql"
download airbnb    "https://raw.githubusercontent.com/neondatabase-labs/postgres-sample-dbs/main/airbnb.sql"
download lms       "https://raw.githubusercontent.com/nicedoc/lms-db-schema/master/schema.sql"

echo ""
echo "Downloaded schemas:"
ls -1 "$SCHEMAS_DIR"/*.sql 2>/dev/null | sed 's|.*/||' || echo "  (none)"
