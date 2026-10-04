"""Integrated verification suite for Stage 2 tools, guardrails, and model discovery."""
from sales_agent.tools import list_tables, describe_table, run_sql
from sales_agent.models import discover_model

def test_stage2():
    print("1. Testing Table Discovery...")
    tables = list_tables()
    table_names = [t["table"] for t in tables]
    assert "orders" in table_names, f"Expected 'orders' in {table_names}"
    assert "customers" in table_names, f"Expected 'customers' in {table_names}"
    assert "products" in table_names, f"Expected 'products' in {table_names}"
    print(f"   ✓ Discovered {len(tables)} tables: {table_names}")

    print("\n2. Testing Schema Description...")
    cols = describe_table("sales.orders")
    assert isinstance(cols, list), f"Expected list of columns, got {cols}"
    col_names = [c["column"] for c in cols]
    assert "total_amount" in col_names, f"Expected 'total_amount' in {col_names}"
    print(f"   ✓ sales.orders columns verified: {col_names}")

    print("\n3. Testing Read-Only Tripwires & Query Sanitization...")
    # Assert blocked mutations
    blocked = run_sql("DROP TABLE sales.orders;")
    assert "error" in blocked, "Expected error on DROP statement"
    
    blocked_insert = run_sql("INSERT INTO sales.orders VALUES (1, 1, 1, 10, 'delivered', NOW());")
    assert "error" in blocked_insert, "Expected error on INSERT statement"
    
    # Assert query execution with and without trailing semicolons
    res_clean = run_sql("SELECT COUNT(*) FROM sales.orders")
    res_semi = run_sql("SELECT COUNT(*) FROM sales.orders;")
    assert "rows" in res_clean and len(res_clean["rows"]) > 0, "Failed clean SELECT"
    assert "rows" in res_semi and len(res_semi["rows"]) > 0, "Failed semicolon SELECT"
    print("   ✓ Guardrails blocked DDL/DML and sanitized SQL subqueries.")

    print("\n4. Testing Dynamic Model Discovery...")
    model_name = discover_model()
    assert isinstance(model_name, str) and len(model_name) > 0, "Model discovery returned invalid string"
    print(f"   ✓ Discovered active Gemini endpoint: {model_name}")

    print("\nStage 2 All Checks Passed.")

if __name__ == "__main__":
    test_stage2()
