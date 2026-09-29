"""FastMCP server exposing sales database tools via JSON-RPC over stdio."""
import sys
from pathlib import Path

# Ensure project root is present in sys.path when executed directly or via python -m
project_root = Path(__file__).resolve().parents[2]
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from fastmcp import FastMCP
from sales_agent.tools import search_schema, run_sql

# Instantiate FastMCP server per Stage S4.1 specification
mcp = FastMCP("Sales DB Server")

@mcp.tool()
def mcp_search_schema(query: str) -> list[dict]:
    """Search sales DB schema docs to find relevant tables and columns."""
    return search_schema(query)

@mcp.tool()
def mcp_run_sql(sql: str) -> dict:
    """Run a read-only SELECT against the sales database (max 20 rows)."""
    return run_sql(sql)

if __name__ == "__main__":
    mcp.run()
