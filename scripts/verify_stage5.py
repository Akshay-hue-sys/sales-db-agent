"""Verification script for Stage 5: Inspect DuckDB trace analytics."""
from pathlib import Path
import duckdb

DUCKDB_PATH = Path(__file__).resolve().parents[1] / "sales-db-agent.duckdb"


def main():
    if not DUCKDB_PATH.exists():
        print(f"[FAIL] DuckDB file not found at: {DUCKDB_PATH}")
        return

    conn = duckdb.connect(str(DUCKDB_PATH), read_only=True)

    print("=== Stage 5.2: DuckDB Trace Analytics Verification ===\n")

    # 1. Inspect Tables in the 'traces' Schema
    tables = conn.execute("""
        SELECT table_name 
        FROM information_schema.tables 
        WHERE table_schema = 'traces'
        ORDER BY table_name;
    """).fetchall()
    print("Tables found in 'traces' schema:")
    for (t,) in tables:
        print(f"  - traces.{t}")

    # 2. Overall Record and Session Counts
    summary = conn.execute("""
        SELECT 
            count(*) AS total_records,
            count(DISTINCT session_id) AS unique_sessions
        FROM traces.log_records;
    """).fetchone()
    print(f"\nTotal Trace Records : {summary[0]}")
    print(f"Unique Sessions     : {summary[1]}")

    # 3. Event Type Breakdown
    print("\nEvent Type Breakdown:")
    events = conn.execute("""
        SELECT 
            type, 
            count(*) AS event_count
        FROM traces.log_records
        GROUP BY type
        ORDER BY event_count DESC;
    """).fetchall()
    for ev_type, count in events:
        print(f"  {ev_type:<15}: {count}")

    # 4. Tool Usage Analytics (Reading from dlt-flattened column: data__name)
    print("\nTool Invocations (Extracted from data__name):")
    tools = conn.execute("""
        SELECT 
            COALESCE(data__name, 'unknown') AS tool_name,
            count(*) AS call_count
        FROM traces.log_records
        WHERE type = 'tool_use'
        GROUP BY tool_name
        ORDER BY call_count DESC;
    """).fetchall()

    for tool_name, calls in tools:
        print(f"  {tool_name:<20}: {calls} call(s)")

    # 5. Token Consumption Analytics (Reading from data__total_tokens)
    token_stats = conn.execute("""
        SELECT 
            COALESCE(MAX(data__total_tokens), 0) AS max_tokens_per_session,
            COALESCE(AVG(data__total_tokens), 0) AS avg_tokens_per_step
        FROM traces.log_records
        WHERE type = 'usage';
    """).fetchone()
    print(f"\nToken Consumption Stats:")
    print(f"  Peak Session Tokens : {token_stats[0]}")
    print(f"  Avg Tokens per Step : {token_stats[1]:.1f}")

    print("\n[PASS] Stage 5.2 DuckDB verification complete.")


if __name__ == "__main__":
    main()
