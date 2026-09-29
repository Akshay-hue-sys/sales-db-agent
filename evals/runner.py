"""Test harness: Runs benchmark suites against the agent and records evaluation metrics."""
import json
import time
from pathlib import Path
from typing import Any, Dict, List

from evals.evaluator import Evaluator
from sales_agent.agent import run_agent

SUITE_PATH = Path(__file__).parent / "test_suite.json"
RESULTS_PATH = Path(__file__).parent / "results.json"


def run_benchmark() -> List[Dict[str, Any]]:
    """Execute the full evaluation benchmark and aggregate results."""
    if not SUITE_PATH.exists():
        raise FileNotFoundError(f"Test suite not found at {SUITE_PATH}")

    test_cases = json.loads(SUITE_PATH.read_text(encoding="utf-8"))
    evaluator = Evaluator()
    results = []

    print(f"=== Starting Evaluation Run: {len(test_cases)} Test Cases ===\n")

    for tc in test_cases:
        tc_id = tc["id"]
        question = tc["question"]
        print(f"-> Running [{tc['tier']}] {tc_id}...")

        start_time = time.time()
        try:
            agent_response = run_agent(question)
            duration = round(time.time() - start_time, 2)
            error = None
        except Exception as exc:
            agent_response = ""
            duration = round(time.time() - start_time, 2)
            error = str(exc)

        # Apply Evaluation Stack
        if error:
            l1_eval = {"l1_passed": False, "reasons": [f"Execution error: {error}"]}
            l2_eval = {"judge_score": 1, "judge_reason": f"Agent crashed: {error}"}
        else:
            l1_eval = evaluator.evaluate_deterministic(tc, agent_response)
            l2_eval = evaluator.evaluate_judge(tc, agent_response)

        record = {
            "id": tc_id,
            "tier": tc["tier"],
            "question": question,
            "duration_sec": duration,
            "agent_response": agent_response,
            "l1_passed": l1_eval["l1_passed"],
            "l1_reasons": l1_eval["reasons"],
            "judge_score": l2_eval["judge_score"],
            "judge_reason": l2_eval["judge_reason"],
            "error": error,
        }
        results.append(record)

        status = "PASS" if record["l1_passed"] and record["judge_score"] >= 4 else "FAIL"
        print(f"   [{status}] L1: {record['l1_passed']} | Judge: {record['judge_score']}/5 | Latency: {duration}s")
        if record["l1_reasons"]:
            print(f"   Notes: {'; '.join(record['l1_reasons'])}")

    # Persist structured results
    RESULTS_PATH.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[DONE] Evaluation run saved to {RESULTS_PATH}")
    return results


def print_summary(results: List[Dict[str, Any]]) -> None:
    """Render a terminal score card."""
    total = len(results)
    l1_passes = sum(1 for r in results if r["l1_passed"])
    avg_judge = sum(r["judge_score"] for r in results) / total if total else 0
    avg_latency = sum(r["duration_sec"] for r in results) / total if total else 0

    print("\n" + "=" * 55)
    print("           BENCHMARK EVALUATION SUMMARY           ")
    print("=" * 55)
    print(f"Total Test Cases      : {total}")
    print(f"L1 Deterministic Pass : {l1_passes}/{total} ({l1_passes / total * 100:.1f}%)")
    print(f"Average Judge Score   : {avg_judge:.2f} / 5.0")
    print(f"Average Turn Latency  : {avg_latency:.2f}s")
    print("=" * 55)


if __name__ == "__main__":
    results = run_benchmark()
    print_summary(results)
