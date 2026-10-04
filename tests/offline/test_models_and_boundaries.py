import importlib
import io
import socket
from types import SimpleNamespace as NS

import pytest
from google.genai import types

from sales_agent.models import ModelError, ModelFailure, classify_error, discover_model, generate


class Error(Exception):
    def __init__(self, code):
        self.code = code
        super().__init__("PRIVATE_ERROR_BODY")


@pytest.mark.parametrize(
    "code,category",
    [
        (400, "INVALID_REQUEST"),
        (401, "AUTHENTICATION"),
        (403, "PERMISSION"),
        (404, "MODEL_NOT_FOUND"),
        (408, "TIMEOUT"),
        (429, "QUOTA"),
        (503, "TRANSIENT_PROVIDER"),
    ],
)
def test_model_taxonomy(code, category):
    assert classify_error(Error(code)) == category


@pytest.mark.parametrize("code", [400, 401, 403, 404, 408, 429])
def test_no_retry_or_rotation_for_terminal_errors(code):
    calls = []

    def fail(**kw):
        calls.append(kw["model"])
        raise Error(code)

    client = NS(models=NS(generate_content=fail))
    with pytest.raises(ModelError) as exc:
        generate(
            client,
            model="one-model",
            contents=[],
            config=types.GenerateContentConfig(),
            deadline=20,
            clock=lambda: 0,
            sleep=lambda _: pytest.fail("Must not wait"),
        )
    assert calls == ["one-model"] and "PRIVATE_ERROR_BODY" not in str(exc.value)


def test_transient_retries_are_bounded():
    calls = []
    waits = []

    def fail(**kw):
        calls.append(1)
        raise Error(503)

    with pytest.raises(ModelError):
        generate(
            NS(models=NS(generate_content=fail)),
            model="one",
            contents=[],
            config=types.GenerateContentConfig(),
            deadline=20,
            clock=lambda: 0,
            sleep=waits.append,
        )
    assert len(calls) == 3 and waits == [1, 2]


def test_retry_deadline():
    def fail(**kw):
        raise Error(503)

    with pytest.raises(ModelError) as exc:
        generate(
            NS(models=NS(generate_content=fail)),
            model="one",
            contents=[],
            config=types.GenerateContentConfig(),
            deadline=0.5,
            clock=lambda: 0,
            sleep=lambda _: pytest.fail("No wait"),
        )
    assert exc.value.category == ModelFailure.TIMEOUT


def test_inventory_and_configured_model():
    client = NS(
        models=NS(
            list=lambda **kw: [
                NS(name="models/gemini-test-flash", supported_actions=["generateContent"]),
                NS(name="models/embedding", supported_actions=["embedContent"]),
            ]
        )
    )
    assert discover_model(client) == "gemini-test-flash"
    assert discover_model(client, preferred="gemini-test-flash") == "gemini-test-flash"
    with pytest.raises(ModelError):
        discover_model(client, preferred="nonexistent")


def test_runtime_imports_need_no_services():
    for name in [
        "sales_agent.agent",
        "sales_agent.tools",
        "sales_agent.db",
        "sales_agent.schema_store",
        "sales_agent.embedder",
        "sales_agent.models",
        "sales_agent.cli",
        "sales_db_agent",
    ]:
        assert importlib.import_module(name)


def test_offline_guards_are_active(tmp_path):
    import psycopg
    from dotenv import load_dotenv
    from google import genai

    for action in [
        lambda: socket.getaddrinfo("example.com", 443),
        lambda: socket.socket(),
        load_dotenv,
        genai.Client,
        psycopg.connect,
        lambda: io.open(tmp_path / ".env", "w"),
        lambda: io.open(tmp_path / "private.pem", "w"),
    ]:
        with pytest.raises(RuntimeError):
            action()


def test_configuration_is_absent_in_offline_process():
    import os

    assert not any(n in os.environ for n in ["DATABASE_URL", "GEMINI_API_KEY", "GOOGLE_API_KEY"])


def test_request_timeout_respects_configuration_and_remaining_budget():
    seen = []
    client = NS(
        models=NS(generate_content=lambda **kw: seen.append(kw["config"].http_options.timeout) or NS(text="ok"))
    )
    config = types.GenerateContentConfig(http_options=types.HttpOptions(timeout=2000))
    generate(client, model="fake", contents=[], config=config, deadline=10, clock=lambda: 0)
    generate(client, model="fake", contents=[], config=config, deadline=0.5, clock=lambda: 0)
    assert seen == [2000, 500]


def test_cli_one_shot_uses_supported_service(monkeypatch, capsys):
    from sales_agent import cli
    import sys

    calls = []

    class FakeAgent:
        model = None

        def run(self, question):
            calls.append(question)
            return "supported answer"

    monkeypatch.setattr(cli, "SalesAgent", FakeAgent)
    monkeypatch.setattr(sys, "argv", ["sales-agent", "What tables exist?"])
    cli.main()
    assert calls == ["What tables exist?"] and "supported answer" in capsys.readouterr().out


def test_installed_sdk_can_describe_all_five_tools_without_client():
    from sales_agent.agent import TOOL_FUNCS

    declarations = [
        types.FunctionDeclaration.from_callable_with_api_option(callable=f, api_option="GEMINI_API")
        for f in TOOL_FUNCS.values()
    ]
    assert {d.name for d in declarations} == set(TOOL_FUNCS)
    sql = next(d for d in declarations if d.name == "run_sql")
    assert sql.parameters.properties["sql"].type == types.Type.STRING


def test_lazy_client_uses_only_gemini_api_and_bounded_timeout(monkeypatch):
    from google import genai
    from sales_agent.models import get_client

    seen = []
    monkeypatch.setattr(genai, "Client", lambda **kw: seen.append(kw) or "fake-client")
    assert get_client(2) == "fake-client"
    assert seen[0]["vertexai"] is False and seen[0]["http_options"].timeout == 2000


def test_catalog_cannot_iterate_without_bound():
    def endless():
        while True:
            yield NS(name="models/gemini-test-flash", supported_actions=["generateContent"])

    client = NS(models=NS(list=lambda **kw: endless()))
    with pytest.raises(ModelError) as exc:
        discover_model(client)
    assert exc.value.category == ModelFailure.CONFIGURATION


def test_expired_catalog_budget_does_not_request_inventory():
    client = NS(models=NS(list=lambda **kw: pytest.fail("No inventory request")))
    with pytest.raises(ModelError) as exc:
        discover_model(client, deadline=1, clock=lambda: 2)
    assert exc.value.category == ModelFailure.TIMEOUT


def test_nontransient_provider_failure_is_not_retried():
    calls = []

    def fail(**kw):
        calls.append(1)
        raise Error(501)

    with pytest.raises(ModelError) as exc:
        generate(
            NS(models=NS(generate_content=fail)),
            model="fake",
            contents=[],
            config=types.GenerateContentConfig(),
            deadline=20,
            clock=lambda: 0,
            sleep=lambda _: pytest.fail("No retry"),
        )
    assert exc.value.category == ModelFailure.PROVIDER_FAILURE and calls == [1]
