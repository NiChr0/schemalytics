"""Extract schema from PostgreSQL using SQLAlchemy."""
from sqlalchemy import create_engine, inspect
from schemalytics.models import Schema, Table, Column, ForeignKey


def extract_schema(connection_string: str) -> Schema:
    """Extract full schema from Postgres database."""
    engine = create_engine(connection_string)
    inspector = inspect(engine)
    
    tables = []
    for table_name in inspector.get_table_names():
        columns = [
            Column(
                name=col["name"],
                data_type=str(col["type"]),
                nullable=col["nullable"],
            )
            for col in inspector.get_columns(table_name)
        ]
        
        pk = inspector.get_pk_constraint(table_name)
        primary_key = pk["constrained_columns"] if pk else None
        
        foreign_keys = [
            ForeignKey(
                column=fk["constrained_columns"][0],
                references_table=fk["referred_table"],
                references_column=fk["referred_columns"][0],
            )
            for fk in inspector.get_foreign_keys(table_name)
            if fk["constrained_columns"]
        ]
        
        tables.append(Table(
            name=table_name,
            columns=columns,
            primary_key=primary_key,
            foreign_keys=foreign_keys,
        ))
    
    return Schema(tables=tables)
