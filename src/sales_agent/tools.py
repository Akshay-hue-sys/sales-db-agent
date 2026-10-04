"""Five controlled service desks. Only run_sql produces business evidence."""

import json

from sales_agent.contracts import Status, error_result
from sales_agent.db import get_read_conn
from sales_agent.sql_policy import TABLES, validate_sql

MAX_ROWS, MAX_COLUMNS, MAX_CELL_CHARS, MAX_RESULT_BYTES = 20, 32, 2048, 65536


def _read(query, params=()):
    with get_read_conn() as conn:
        return conn.execute(query, params).fetchall()


def _db_error(exc):
    if getattr(exc, "sqlstate", None) == "57014":
        return error_result(Status.TIMEOUT, "STATEMENT_TIMEOUT", "Database statement timed out.")
    return error_result(Status.DATABASE_ERROR, "DATABASE_ERROR", "Database operation failed.")


def _table_name(table_name):
    if not isinstance(table_name, str):
        raise ValueError
    name = table_name.strip()
    if name.startswith("sales."):
        name = name[6:]
    if name not in TABLES:
        raise ValueError
    return name


def list_tables() -> list[dict]:
    """List approved sales tables. Returns schema/table pairs or a typed error."""
    try:
        rows = _read("""SELECT table_schema, table_name FROM information_schema.tables
            WHERE table_schema='sales' AND table_name IN ('customers','products','orders') ORDER BY 1,2""")
        return [{"schema": r[0], "table": r[1]} for r in rows]
    except Exception as exc:
        return _db_error(exc)


def describe_table(table_name: str) -> list[dict]:
    """Describe approved sales table columns. table_name: sales.orders etc."""
    try:
        name = _table_name(table_name)
    except ValueError:
        return error_result(Status.INVALID_REQUEST, "TABLE_NOT_ALLOWED", "Unknown or unapproved sales table.")
    try:
        rows = _read(
            """SELECT column_name,data_type,is_nullable FROM information_schema.columns
            WHERE table_schema='sales' AND table_name=%s ORDER BY ordinal_position""",
            (name,),
        )
        return [{"column": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in rows]
    except Exception as exc:
        return _db_error(exc)


def get_schema(table_name: str | None = None) -> dict:
    """Inventory sales tables or retrieve exact columns and foreign-key links."""
    if table_name is None:
        result = list_tables()
        return result if isinstance(result, dict) else {"tables": [f"{r['schema']}.{r['table']}" for r in result]}
    try:
        name = _table_name(table_name)
    except ValueError:
        return error_result(Status.INVALID_REQUEST, "TABLE_NOT_ALLOWED", "Unknown or unapproved sales table.")
    columns = describe_table(name)
    if isinstance(columns, dict):
        return columns
    if not columns:
        return error_result(Status.NO_DATA, "TABLE_NOT_FOUND", "Approved table has no visible columns.")
    try:
        rows = _read(
            """SELECT kcu.column_name, ccu.table_schema, ccu.table_name, ccu.column_name
            FROM information_schema.table_constraints tc
            JOIN information_schema.key_column_usage kcu
            ON tc.constraint_name=kcu.constraint_name AND tc.table_schema=kcu.table_schema AND tc.table_name=kcu.table_name
            JOIN information_schema.constraint_column_usage ccu
            ON ccu.constraint_name=tc.constraint_name AND ccu.table_schema=tc.table_schema
            WHERE tc.constraint_type='FOREIGN KEY' AND tc.table_schema='sales' AND tc.table_name=%s""",
            (name,),
        )
        return {
            "table": f"sales.{name}",
            "columns": [{"name": c["column"], "type": c["type"], "nullable": c["nullable"]} for c in columns],
            "foreign_keys": [
                {"column": r[0], "references_table": f"{r[1]}.{r[2]}", "references_column": r[3]} for r in rows
            ],
        }
    except Exception as exc:
        return _db_error(exc)


def search_schema(query: str) -> list[dict]:
    """Find up to five schema/business guidance cards, never current sales facts."""
    if not isinstance(query, str) or not query.strip() or len(query) > 1000:
        return error_result(Status.INVALID_REQUEST, "INVALID_QUERY", "Invalid schema search query.")
    try:
        from sales_agent.schema_store import search_docs

        return search_docs(query, k=5)
    except Exception:
        return error_result(Status.RETRIEVAL_ERROR, "RETRIEVAL_ERROR", "Schema guidance retrieval failed.")


def run_sql(sql: str) -> dict:
    """Run one analytical SELECT over qualified sales tables, with bounded results."""
    try:
        normalized = validate_sql(sql)
    except ValueError as exc:
        return error_result(Status.POLICY_REJECTION, "SQL_POLICY", str(exc))
    try:
        with get_read_conn() as conn:
            cursor = conn.execute(f"SELECT * FROM ({normalized}) AS _agent_sub LIMIT {MAX_ROWS + 1}")
            columns = [d.name for d in cursor.description] if cursor.description else []
            rows = cursor.fetchmany(MAX_ROWS + 1)
        if len(columns) > MAX_COLUMNS or len(set(columns)) != len(columns):
            return error_result(Status.POLICY_REJECTION, "RESULT_BOUND", "Too many or ambiguous result columns.")
        if any(len(row) != len(columns) for row in rows):
            return error_result(Status.DATABASE_ERROR, "RESULT_SHAPE", "Unexpected database result shape.")
        converted = [[None if cell is None else str(cell) for cell in row] for row in rows[:MAX_ROWS]]
        if any(cell is not None and len(cell) > MAX_CELL_CHARS for row in converted for cell in row):
            return error_result(Status.POLICY_REJECTION, "RESULT_BOUND", "Result cell exceeded its size bound.")
        result = {
            "status": str(Status.SUCCESS if rows else Status.NO_DATA),
            "sql": normalized,
            "columns": columns,
            "rows": converted,
            "truncated": len(rows) > MAX_ROWS,
        }
        if len(json.dumps(result).encode()) > MAX_RESULT_BYTES:
            return error_result(Status.POLICY_REJECTION, "RESULT_BOUND", "Result exceeded its byte bound.")
        return result
    except Exception as exc:
        return _db_error(exc)
