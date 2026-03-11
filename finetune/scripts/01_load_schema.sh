#!/bin/bash
# Load a SQL dump into Docker Postgres and run schemalytics extract.
# Run from repo root: bash finetune/scripts/01_load_schema.sh <sql_dump_path> <db_name>
#
# Prerequisites:
#   - Docker Postgres container named "northwind-test" on localhost:5432
#   - schemalytics installed in current venv

set -e

CONTAINER="northwind-test"

if [ "$#" -ne 2 ]; then
    echo "Usage: bash finetune/scripts/01_load_schema.sh <sql_dump_path> <db_name>"
    echo "Example: bash finetune/scripts/01_load_schema.sh finetune/schemas/sakila.sql sakila"
    exit 1
fi

SQL_DUMP="$1"
DB_NAME="$2"
OUTPUT="finetune/extracted/${DB_NAME}.json"

if [ ! -f "$SQL_DUMP" ]; then
    echo "ERROR: SQL dump not found: $SQL_DUMP"
    exit 1
fi

echo "==> Dropping and recreating database: $DB_NAME"
docker exec -i "$CONTAINER" psql -U postgres -c "DROP DATABASE IF EXISTS \"${DB_NAME}\";" postgres
docker exec -i "$CONTAINER" psql -U postgres -c "CREATE DATABASE \"${DB_NAME}\";" postgres

echo "==> Loading SQL dump: $SQL_DUMP"
if ! docker exec -i "$CONTAINER" psql -U postgres -d "$DB_NAME" < "$SQL_DUMP" > /dev/null 2>&1; then
    echo "WARNING: Some statements failed during load (may be harmless for schema-only dumps)"
fi

echo "==> Running schemalytics extract..."
mkdir -p finetune/extracted
schemalytics extract \
    -c "postgresql://postgres:mypassword@localhost:5432/${DB_NAME}" \
    -o "$OUTPUT"

echo "==> Done: $OUTPUT"
