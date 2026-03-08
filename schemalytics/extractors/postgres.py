"""Extract schema from PostgreSQL using SQLAlchemy."""
from sqlalchemy import create_engine, inspect
from schemalytics.models import Schema, Table, Column, ForeignKey

# PostgreSQL system schemas to always exclude.
_SYSTEM_SCHEMAS = {"pg_catalog", "information_schema", "pg_toast"}


def extract_schema(connection_string: str) -> Schema:
    """Extract full schema from all user schemas in a Postgres database.

    Excludes pg_catalog, information_schema, pg_toast, and any schema
    whose name starts with 'pg_' (covers pg_temp_*, pg_toast_temp_*, etc.).
    """
    engine = create_engine(connection_string)
    inspector = inspect(engine)

    user_schemas = [
        s for s in inspector.get_schema_names()
        if s not in _SYSTEM_SCHEMAS and not s.startswith("pg_")
    ]

    tables = []
    skipped_cols: list[tuple[str, str, str]] = []
    for schema_name in user_schemas:
        for table_name in inspector.get_table_names(schema=schema_name):
            raw_cols = inspector.get_columns(table_name, schema=schema_name)
            columns = []
            for col in raw_cols:
                type_str = str(col["type"])
                if type_str.upper() == "NULLTYPE":
                    skipped_cols.append((f"{schema_name}.{table_name}", col["name"], type_str))
                    continue
                columns.append(Column(
                    name=col["name"],
                    data_type=type_str,
                    nullable=col["nullable"],
                ))

            pk = inspector.get_pk_constraint(table_name, schema=schema_name)
            primary_key = pk["constrained_columns"] if pk else None

            foreign_keys = []
            for fk in inspector.get_foreign_keys(table_name, schema=schema_name):
                if not fk["constrained_columns"]:
                    continue
                # Cross-schema FKs: prefix referred_table with the referred schema.
                referred_schema = fk.get("referred_schema")
                ref_table = (
                    f"{referred_schema}.{fk['referred_table']}"
                    if referred_schema and referred_schema != schema_name
                    else fk["referred_table"]
                )
                foreign_keys.append(ForeignKey(
                    column=fk["constrained_columns"][0],
                    references_table=ref_table,
                    references_column=fk["referred_columns"][0],
                ))

            tables.append(Table(
                name=table_name,
                schema_name=schema_name,
                columns=columns,
                primary_key=primary_key,
                foreign_keys=foreign_keys,
            ))

    if skipped_cols:
        import sys
        print(
            f"\nWarning: {len(skipped_cols)} column(s) skipped — unsupported type "
            "(e.g. XML, custom composite). These will be absent from the generated models:",
            file=sys.stderr,
        )
        for tbl, col_name, col_type in skipped_cols:
            print(f"  {tbl}.{col_name}  ({col_type})", file=sys.stderr)

    return Schema(tables=tables)
