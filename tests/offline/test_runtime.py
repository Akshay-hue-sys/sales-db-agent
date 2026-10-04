import json
from types import SimpleNamespace as NS

import pytest
from google.genai import types

from sales_agent.agent import TOOL_FUNCS, SalesAgent, run_agent
from sales_agent.config import AgentConfig
from sales_agent.contracts import Status
from sales_agent.trace import TraceLogger


def response(text=None, calls=(), tokens=1, missing_content=False):
    parts = [
        types.Part(function_call=types.FunctionCall(name=n, args=a if isinstance(a, dict) else {})) for n, a in calls
    ]
    return NS(
        text=text,
        function_calls=[NS(name=n, args=a, id=None) for n, a in calls],
        candidates=[]
        if missing_content
        else [NS(content=types.Content(role="model", parts=parts or [types.Part(text=text or "")]))],
        usage_metadata=NS(total_token_count=tokens),
    )


class FakeClient:
    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []
        self.models = self

    def generate_content(self, **kwargs):
        self.calls.append(kwargs)
        r = next(self.responses)
        if isinstance(r, Exception):
            raise r
        return r


def service(tmp_path, responses, replacements=None, config=None, clock=None):
    tools = {name: (lambda **kwargs: {"tables": ["sales.orders"]}) for name in TOOL_FUNCS}
    tools.update(replacements or {})
    client = FakeClient(responses)
    kwargs = {} if clock is None else {"clock": clock}
    agent = SalesAgent(
        model="fake-model",
        client=client,
        tools=tools,
        config=config,
        trace_factory=lambda q: TraceLogger(q, directory=tmp_path),
        sleep=lambda _: None,
        **kwargs,
    )
    return agent, client


def events(tmp_path):
    return [json.loads(line) for line in (tmp_path / "log_records.jsonl").read_text().splitlines()]


def test_no_tool_help_returns_text_and_closes(tmp_path):
    a, c = service(tmp_path, [response('{"kind":"help"}')])
    assert "inspect sales schemas" in a.run("What can you do?")
    assert events(tmp_path)[-1]["data"]["reason"] == "SUCCESS"
    assert len(c.calls) == 1


def test_known_call_and_schema_only_answer(tmp_path):
    called = []
    a, c = service(
        tmp_path,
        [response(calls=[("get_schema", {})]), response('{"kind":"schema"}')],
        {"get_schema": lambda: called.append(1) or {"tables": ["sales.orders"]}},
    )
    result = a.answer("What tables exist?")
    assert called == [1] and result.evidence_type == "schema" and "sales.orders" in result.answer_text
    assert c.calls[-1]["contents"][-1].parts[0].function_response.response["tables"] == ["sales.orders"]


@pytest.mark.parametrize(
    "name,args,code",
    [
        ("not_a_tool", {}, "UNKNOWN_TOOL"),
        ("get_schema", [], "INVALID_ARGUMENTS"),
        ("get_schema", {"unexpected": 1}, "INVALID_ARGUMENTS"),
        ("run_sql", {}, "INVALID_ARGUMENTS"),
        ("run_sql", {"sql": 42}, "INVALID_ARGUMENTS"),
    ],
)
def test_bad_tool_requests_do_not_execute(tmp_path, name, args, code):
    called = []
    a, c = service(
        tmp_path,
        [response(calls=[(name, args)]), response('{"kind":"help"}')],
        {"get_schema": lambda **kw: called.append(1)},
    )
    a.run("Help")
    payload = c.calls[-1]["contents"][-1].parts[0].function_response.response
    assert payload["error_code"] == code and called == []


def test_tool_exception_is_sanitized(tmp_path):
    def boom():
        raise RuntimeError("SECRET_SENTINEL connection string")

    a, c = service(tmp_path, [response(calls=[("get_schema", {})]), response('{"kind":"help"}')], {"get_schema": boom})
    a.run("Help")
    payload = c.calls[-1]["contents"][-1].parts[0].function_response.response
    assert payload["status"] == "TOOL_ERROR" and "SECRET_SENTINEL" not in str(payload)


def test_duplicate_never_executes_twice(tmp_path):
    called = []
    a, c = service(
        tmp_path,
        [response(calls=[("get_schema", {})]), response(calls=[("get_schema", {})]), response('{"kind":"schema"}')],
        {"get_schema": lambda: called.append(1) or {"tables": ["sales.orders"]}},
    )
    a.run("What tables?")
    assert called == [1]
    assert c.calls[-1]["contents"][-1].parts[0].function_response.response["error_code"] == "DUPLICATE_TOOL"
    assert [e["data"]["status"] for e in events(tmp_path) if e["type"] == "tool_outcome"] == [
        "SUCCESS",
        "POLICY_REJECTION",
    ]


def test_step_budget(tmp_path):
    a, c = service(tmp_path, [response(calls=[("get_schema", {})])] * 2, config=AgentConfig(max_steps=2))
    assert "step limit" in a.run("What tables?") and len(c.calls) == 2
    assert events(tmp_path)[-1]["data"]["reason"] == "POLICY_REJECTION"


@pytest.mark.parametrize(
    "r", [response(""), response(None), response(calls=[("get_schema", {})], missing_content=True)]
)
def test_malformed_response_closes(tmp_path, r):
    a, c = service(tmp_path, [r])
    result = a.answer("Question")
    assert result.status == Status.MODEL_ERROR
    assert events(tmp_path)[-1]["data"]["reason"] == "MALFORMED_RESPONSE"


def test_text_plus_calls_executes_calls_not_premature_text(tmp_path):
    a, c = service(tmp_path, [response("Revenue is 5000", calls=[("get_schema", {})]), response('{"kind":"schema"}')])
    assert "5000" not in a.run("What columns?") and len(c.calls) == 2


def test_no_sql_cannot_emit_numeric_business_claim(tmp_path):
    a, c = service(tmp_path, [response("Revenue is 2351.05")])
    result = a.answer("What is delivered revenue?")
    assert result.status == Status.POLICY_REJECTION and "2351.05" not in result.answer_text


def observation():
    return {
        "status": "SUCCESS",
        "sql": "SELECT SUM(total_amount) AS revenue FROM sales.orders WHERE status = 'delivered'",
        "columns": ["revenue"],
        "rows": [["2351.05"]],
        "truncated": False,
    }


def test_structured_evidence_renders_exact_cells(tmp_path):
    a, c = service(
        tmp_path,
        [response(calls=[("run_sql", {"sql": "query"})]), response('{"evidence_id":"sql_1","row_indices":[0]}')],
        {"run_sql": lambda sql: observation()},
    )
    result = a.answer("Delivered revenue?")
    assert result.status == Status.SUCCESS and result.supporting_rows == (("2351.05",),)
    assert "revenue: 2351.05" in result.answer_text and result.sql_used
    assert c.calls[-1]["contents"][-1].parts[0].function_response.response["evidence_id"] == "sql_1"


@pytest.mark.parametrize(
    "final",
    [
        '{"evidence_id":"sql_1","row_indices":[0],"explanation":"5000"}',
        '{"evidence_id":"invented","row_indices":[0]}',
        '{"evidence_id":"sql_1","row_indices":[99]}',
        '{"evidence_id":"sql_1","row_indices":[true]}',
        "Revenue is 2351.05 or 5000",
    ],
)
def test_matching_numbers_do_not_fake_validation(tmp_path, final):
    a, c = service(
        tmp_path,
        [response(calls=[("run_sql", {"sql": "query"})]), response(final)],
        {"run_sql": lambda sql: observation()},
    )
    result = a.answer("Revenue?")
    assert result.status == Status.POLICY_REJECTION and "5000" not in result.answer_text


def test_privacy_and_finally_on_exception(tmp_path):
    a, c = service(tmp_path, [RuntimeError("SECRET_SENTINEL")])
    a.run("SECRET_SENTINEL private question")
    data = (tmp_path / "log_records.jsonl").read_text()
    assert "SECRET_SENTINEL" not in data and data.count("session_end") == 1


def test_cumulative_token_budget(tmp_path):
    a, c = service(
        tmp_path,
        [response(calls=[("get_schema", {})], tokens=6), response('{"kind":"schema"}', tokens=6)],
        config=AgentConfig(max_tokens=10),
    )
    assert "budget exceeded" in a.run("Tables?")


def test_invalid_input_does_not_start_runtime(tmp_path):
    a, c = service(tmp_path, [])
    assert a.answer("").status == Status.INVALID_REQUEST and not c.calls


def test_timeout_prevents_tool_execution(tmp_path):
    t = [0]

    def advance(**kw):
        t[0] = 100
        return response(calls=[("get_schema", {})])

    called = []
    a, c = service(tmp_path, [], {"get_schema": lambda: called.append(1)}, clock=lambda: t[0])
    c.generate_content = advance
    assert a.answer("Tables?").status == Status.TIMEOUT and not called


def test_compatibility_api_delegates(tmp_path):
    client = FakeClient([response('{"kind":"help"}')])
    assert "inspect sales schemas" in run_agent(
        "Help", model="fake", client=client, trace_factory=lambda q: TraceLogger(q, directory=tmp_path)
    )
