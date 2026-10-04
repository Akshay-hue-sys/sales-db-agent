import json
from pathlib import Path
from types import SimpleNamespace as NS

import pytest

from evals.evaluator import Evaluator
from sales_agent.contracts import Status
from sales_agent.trace import TraceLogger
from test_runtime import response, service


def test_deterministic_evaluation_does_not_create_client():
    evaluator = Evaluator()
    assert evaluator.client is None
    assert evaluator.evaluate_deterministic({"expected_numeric_answer": 2351.05}, "2351.05")["l1_passed"]


@pytest.mark.parametrize("body", ["{}", '{"score":99}', '{"score":true}', "not JSON"])
def test_invalid_judge_output_not_a_low_quality_score(body):
    client = NS(models=NS(generate_content=lambda **kw: NS(text=body)))
    result = Evaluator(client=client, judge_model="fake").evaluate_judge({"question": "Revenue?"}, "Answer")
    assert result["judge_score"] is None and result["judge_status"] == "MALFORMED_RESPONSE"


def test_quota_judge_failure_stays_unavailable():
    called = []

    def fail(**kw):
        called.append(1)
        exc = RuntimeError("SECRET_SENTINEL")
        exc.code = 429
        raise exc

    result = Evaluator(client=NS(models=NS(generate_content=fail)), judge_model="fake").evaluate_judge(
        {"question": "Revenue?"}, "Answer"
    )
    assert result["judge_score"] is None and result["judge_status"] == "QUOTA" and called == [1]
    assert "SECRET_SENTINEL" not in str(result)


def test_schema_guidance_trace_has_no_descriptions_or_arguments(tmp_path):
    a, c = service(
        tmp_path,
        [response(calls=[("search_schema", {"query": "SECRET_SENTINEL"})]), response('{"kind":"help"}')],
        {
            "search_schema": lambda query: [
                {"id": "doc_orders_total", "description": "SECRET_SENTINEL", "similarity": 0.9}
            ]
        },
    )
    a.run("SECRET_SENTINEL")
    trace = (tmp_path / "log_records.jsonl").read_text()
    assert "SECRET_SENTINEL" not in trace and "doc_orders_total" in trace
    events = [json.loads(line) for line in trace.splitlines()]
    assert len([e for e in events if e["type"] == "model_request"]) == 2


def test_trace_close_idempotent(tmp_path):
    trace = TraceLogger("SECRET_SENTINEL", directory=tmp_path)
    trace.close("SUCCESS")
    trace.close("FAILURE")
    assert (tmp_path / "log_records.jsonl").read_text().count("session_end") == 1


def test_unconfigured_card_metadata_cannot_leak(tmp_path):
    trace = TraceLogger("Question", directory=tmp_path)
    trace.tool_outcome(
        "search_schema", "SUCCESS", 0.1, [{"id": "doc_SECRET_SENTINEL", "similarity": "SECRET_SENTINEL"}]
    )
    assert "SECRET_SENTINEL" not in (tmp_path / "log_records.jsonl").read_text()


def test_retrieval_baseline_references_configured_public_cards():
    from sales_agent.schema_store import read_cards

    ids = {c["id"] for c in read_cards()}
    root = Path(__file__).resolve().parents[2]
    cases = json.loads((root / "evals/retrieval_cases.json").read_text())
    assert len(cases) == 5
    assert all(c["query"] and set(c["expected_any"]) <= ids for c in cases)


def test_trace_write_failure_is_visible_and_does_not_break_answer(tmp_path):
    bad_directory = tmp_path / "file"
    bad_directory.write_text("fixture")
    a, c = service(tmp_path, [response('{"kind":"help"}')])
    a.trace_factory = lambda q: TraceLogger(q, directory=bad_directory)
    result = a.answer("Help")
    assert result.status == Status.SUCCESS and "Trace metadata could not be saved." in result.warnings


def test_schema_setup_does_not_drop_legacy_relations():
    from sales_agent.schema_store import STORE_DDL

    assert "DROP" not in STORE_DDL and "sales.schema_cards" in STORE_DDL
    root = Path(__file__).resolve().parents[2]
    assert "DDL_SCRIPT += STORE_DDL" in (root / "scripts/seed_database.py").read_text()
    assert "INSERT INTO sales.schema_docs" not in (root / "scripts/seed_more_data.py").read_text()
