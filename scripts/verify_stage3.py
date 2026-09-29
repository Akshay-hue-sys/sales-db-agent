"""Automated regression verification for Stage 3 ReAct Agent."""
import sys
from sales_agent.agent import SalesAgent
from sales_agent.tools import run_sql

def run_verification():
    print("[*] Starting Stage 3 Automated Agent Verification...")

    # 1. Fetch deterministic Ground Truth directly from PostgreSQL
    gt_result = run_sql("SELECT SUM(total_amount) FROM sales.orders WHERE status = 'delivered';")
    raw_val = gt_result.get("rows", [[None]])[0][0]
    if raw_val is None:
        print("  [FAIL] Database returned empty rows for delivered orders ground truth.")
        sys.exit(1)
    
    expected_val = str(round(float(raw_val), 2))
    print(f"  [Ground Truth] Delivered revenue in DB: {expected_val}")

    # 2. Run the Autonomous Agent through the ReAct loop
    print("  [Agent Run] Submitting prompt to SalesAgent...")
    agent = SalesAgent()
    prompt = "What is the total revenue from delivered orders?"
    response = agent.run(prompt)
    
    print(f"  [Agent Synthesis] \"{response}\"")

    # 3. Assert Ground Truth is present in the synthesized output
    # Stripping commas/currency formatting for clean string match
    normalized_response = response.replace(",", "").replace("$", "")
    if expected_val in normalized_response:
        print(f"\n[PASS] Agent successfully reasoned, queried SQL, and verified ground truth ({expected_val}).")
        return True
    else:
        print(f"\n[FAIL] Ground truth value {expected_val} was not found in agent answer.")
        return False

if __name__ == "__main__":
    success = run_verification()
    sys.exit(0 if success else 1)
