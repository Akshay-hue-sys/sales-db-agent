"""Evaluation runner: Executes test suite, collects metrics, and reports scorecard."""

import json
import time
from pathlib import Path

from evals.evaluator import Evaluator
from sales_agent.agent import SalesAgent

SUITE_FILE = Path(__file__).parent / "test_suite.json"
RESULTS_FILE = Path(__file__).parent / "results.json"


def run_benchmarks() -> None:
    """Run all configured test cases and print a structured benchmark report."""
    if not SUITE_FILE.exists():
        print(f"Error: Test suite file not found at {SUITE_FILE}")
        return

    test_cases = json.loads(SUITE_FILE.read_text())
    evaluator = Evaluator()
    agent = SalesAgent()
    results = []

    print(f"=== Starting Evaluation Run: {len(test_cases)} Test Cases ===\n")

    for tc in test_cases:
        tc_id = tc["id"]
        tier = tc.get("tier", "unknown")
        question = tc["question"]
        print(f"-> Running [{tier}] {tc_id}...")

        t0 = time.time()
        agent_resp = agent.run(question)
        latency = round(time.time() - t0, 2)

        # L1: Deterministic evaluation (zero token cost)
        l1_result = evaluator.evaluate_deterministic(tc, agent_resp)
        l1_passed = l1_result["l1_passed"]

        # L2: Semantic LLM-as-a-Judge evaluation
        l2_result = evaluator.evaluate_judge(tc, agent_resp)
        judge_score = l2_result["judge_score"]
        judge_reason = l2_result["judge_reason"]

        status = "UNAVAILABLE" if judge_score is None else ("PASS" if l1_passed and judge_score >= 4 else "FAIL")
        print(f"   [{status}] L1: {l1_passed} | Judge: {judge_score}/5 | Latency: {latency}s")
        if not l1_passed:
            print(f"   Notes: {', '.join(l1_result['reasons'])}")

        results.append(
            {
                "id": tc_id,
                "tier": tier,
                "question": question,
                "agent_response": agent_resp,
                "l1_passed": l1_passed,
                "l1_reasons": l1_result["reasons"],
                "judge_score": judge_score,
                "judge_status": l2_result["judge_status"],
                "judge_reason": judge_reason,
                "latency_seconds": latency,
            }
        )

        # Manual benchmark case spacing; not a per-request rate governor.
        time.sleep(4.0)

    RESULTS_FILE.write_text(json.dumps(results, indent=2))
    print(f"\n[DONE] Evaluation run saved to {RESULTS_FILE}\n")

    # Render summary metrics
    total = len(results)
    l1_pass_count = sum(1 for r in results if r["l1_passed"])
    avg_score = sum(r["judge_score"] for r in results if r["judge_score"] is not None) / max(
        1, sum(r["judge_score"] is not None for r in results)
    )
    avg_lat = sum(r["latency_seconds"] for r in results) / total if total else 0.0

    print("=" * 55)
    print("           BENCHMARK EVALUATION SUMMARY           ")
    print("=" * 55)
    print(f"Total Test Cases      : {total}")
    print(f"L1 Deterministic Pass : {l1_pass_count}/{total} ({l1_pass_count / max(1, total) * 100:.1f}%)")
    print(f"Average Judge Score   : {avg_score:.2f} / 5.0")
    print(f"Average Turn Latency  : {avg_lat:.2f}s")
    print("=" * 55)


if __name__ == "__main__":
    run_benchmarks()
