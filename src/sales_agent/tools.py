"""Stage 2 tools: The model emits JSON function arguments; this module executes them."""
import re
from typing import Any
from sales_agent.db import get_conn
from sales_agent.schema_store import search_docs

MAX_ROWS = 20
MAX_SQL_CHARS = 2000

FORBIDDEN = re.compile(
    r"(?i)\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|GRANT|REVOKE|"
    r"COPY|CALL|DO|EXECUTE|MERGE|VACUUM)\b"
)

def list_tables() -> list[dict[str, str]]:
    """List every table and view available in the sales database.
    Call this first to discover what data exists before writing SQL.
    """
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT table_schema, table_name 
            FROM information_schema.tables
            WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
            ORDER BY 1, 2;
        """).fetchall()
    return [{"schema": r[0], "table": r[1]} for r in rows]

def describe_table(table_name: str) -> list[dict[str, Any]] | dict[str, str]:
    """Describe the columns of one sales database table.
    Use after list_tables to learn exact column names and types.
    
    Args:
        table_name: Full table name, e.g. 'sales.orders' or 'sales.customers'.
    """
    clean_name = table_name.strip()
    with get_conn() as conn:
        rows = conn.execute("""
            SELECT column_name, data_type, is_nullable 
            FROM information_schema.columns
            WHERE table_schema || '.' || table_name = %s
            ORDER BY ordinal_position;
        """, (clean_name,)).fetchall()
        
    if not rows:
        return {"error": f"Table '{table_name}' not found. Call list_tables first."}
    return [{"column": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in rows]

def search_schema(query: str) -> list[dict[str, Any]]:
    """Semantic search over sales schema doc cards: identify which tables/columns answer
    a business question (revenue, regions, categories, trends).
    
    Args:
        query: Natural-language phrase describing the business concept.
    """
    return search_docs(query, k=5)

def run_sql(sql: str) -> dict[str, Any]:
    """Execute a READ-ONLY SQL query against the sales database
    and return up to 20 rows. Only SELECT/WITH statements are allowed.
    
    Args:
        sql: A single read-only SQL query. Aggregate with SUM/COUNT/AVG
             and filter with WHERE to keep result sets small.
    """
    cleaned_sql = sql.strip()

    if not re.match(r"(?is)^\s*(SELECT|WITH)\b", cleaned_sql):
        return {"error": "Only SELECT or WITH queries are allowed."}

    if FORBIDDEN.search(cleaned_sql):
        return {"error": "Read-only guard: modifying statements are blocked."}

    if len(cleaned_sql) > MAX_SQL_CHARS:
        return {"error": f"Query too long (max {MAX_SQL_CHARS} characters)."}

    # Strip trailing semicolons and whitespace so SQL subquery wrapping is valid ANSI SQL
    unwrapped_sql = re.sub(r";+\s*$", "", cleaned_sql)
    capped_sql = f"SELECT * FROM ({unwrapped_sql}) AS _agent_sub LIMIT {MAX_ROWS + 1}"

    try:
        with get_conn() as conn:
            cur = conn.execute(capped_sql)
            cols = [d.name for d in cur.description] if cur.description else []
            rows = cur.fetchall()
    except Exception as exc:
        return {"error": f"SQL error: {exc}"}

    if len(rows) > MAX_ROWS:
        return {
            "columns": cols,
            "rows": [list(map(str, r)) for r in rows[:MAX_ROWS]],
            "note": f"Result truncated to {MAX_ROWS} rows; refine query with filters."
        }

    return {
        "columns": cols,
        "rows": [list(map(str, r)) for r in rows]
    }
def get_schema(table_name: str | None = None) -> dict[str, Any]:
    """Inspect tables, columns, and foreign keys directly from the live database.
    
    Args:
        table_name: Optional name of a table (e.g. 'orders' or 'sales.orders').
                    If None, returns all accessible tables in the sales database.
    """
    with get_conn() as conn:
        # Case A: Return table inventory if no table is specified
        if not table_name:
            rows = conn.execute("""
                SELECT table_schema, table_name 
                FROM information_schema.tables
                WHERE table_schema NOT IN ('pg_catalog', 'information_schema')
                ORDER BY table_schema, table_name;
            """).fetchall()
            return {"tables": [f"{r[0]}.{r[1]}" for r in rows]}

        # Case B: Specific table detail inspection
        raw_name = table_name.strip()
        clean_name = raw_name.split(".")[-1] if "." in raw_name else raw_name
        
        # 1. Fetch column specifications
        col_rows = conn.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_schema = 'sales' AND table_name = %s
            ORDER BY ordinal_position;
        """, (clean_name,)).fetchall()

        if not col_rows:
            return {"error": f"Table '{table_name}' not found. Call get_schema() with no args to list tables."}

        # 2. Fetch foreign key relationships
        fk_rows = conn.execute("""
            SELECT
                kcu.column_name,
                ccu.table_name AS foreign_table_name,
                ccu.column_name AS foreign_column_name
            FROM information_schema.table_constraints AS tc
            JOIN information_schema.key_column_usage AS kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
            JOIN information_schema.constraint_column_usage AS ccu
                ON ccu.constraint_name = tc.constraint_name
                AND ccu.table_schema = tc.table_schema
            WHERE tc.constraint_type = 'FOREIGN KEY'
              AND tc.table_schema = 'sales'
              AND tc.table_name = %s;
        """, (clean_name,)).fetchall()

        return {
            "table": f"sales.{clean_name}",
            "columns": [{"name": r[0], "type": r[1], "nullable": r[2] == "YES"} for r in col_rows],
            "foreign_keys": [
                {"column": r[0], "references_table": f"sales.{r[1]}", "references_column": r[2]}
                for r in fk_rows
            ]
        }