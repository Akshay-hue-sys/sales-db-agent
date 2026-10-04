import json
from decimal import Decimal
from types import SimpleNamespace as NS

import pytest

from sales_agent import db, schema_store, tools
from sales_agent.contracts import SQLObservation, Status, render_database_answer
from sales_agent.sql_policy import validate_sql


class Cursor:
    def __init__(self, rows, columns=("revenue",)):
        self.rows = rows
        self.description = [NS(name=n) for n in columns]

    def fetchmany(self, n):
        return self.rows[:n]

    def fetchall(self):
        return self.rows


class Connection:
    def __init__(self, rows=(), columns=("revenue",), error=None):
        self.rows, self.columns, self.error = rows, columns, error
        self.executed = []
        self.closed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.closed = True

    def close(self):
        self.closed = True

    def execute(self, sql, params=()):
        self.executed.append((sql, params))
        if self.error:
            raise self.error
        return Cursor(self.rows, self.columns)


@pytest.mark.parametrize(
    "query",
    [
        "SELECT SUM(total_amount) FROM sales.orders;",
        "SELECT SUM(total_amount) AS revenue FROM sales.orders WHERE status='delivered'",
        "WITH totals AS (SELECT SUM(total_amount) AS n FROM sales.orders) SELECT n FROM totals",
        "SELECT c.region, SUM(o.total_amount) FROM sales.orders o JOIN sales.customers c ON c.id=o.customer_id GROUP BY c.region",
        "SELECT DATE_TRUNC('month', order_date), COUNT(*) FROM sales.orders GROUP BY 1",
        "SELECT 'DROP TABLE is just text' FROM sales.orders",
    ],
)
def test_allowed_analytical_queries(query):
    assert validate_sql(query)


@pytest.mark.parametrize(
    "query",
    [
        "DELETE FROM sales.orders",
        "SELECT 5000 AS revenue",
        "SELECT 1; SELECT 2",
        "WITH x AS (DELETE FROM sales.orders RETURNING *) SELECT * FROM x",
        "SELECT * INTO sales.copy FROM sales.orders",
        "SELECT * FROM sales.orders FOR UPDATE",
        "SELECT pg_sleep(10)",
        "SELECT pg_read_file('/etc/passwd')",
        "SELECT set_config('x','y',false)",
        "SELECT evil_function() FROM sales.orders",
        "SELECT public.evil() FROM sales.orders",
        "SELECT * FROM public.secret",
        "SELECT * FROM orders",
        "SELECT * FROM sales.schema_cards",
        "SELECT * FROM sales.orders TABLESAMPLE SYSTEM (100)",
        "WITH RECURSIVE x AS (SELECT 1 UNION ALL SELECT 1 FROM x) SELECT * FROM x",
        "SELECT 'x'::custom_type FROM sales.orders",
    ],
)
def test_unsafe_queries_rejected(query):
    with pytest.raises(ValueError):
        validate_sql(query)


def test_sql_rows_null_and_cap(monkeypatch):
    conn = Connection([(Decimal("2351.05"),), (None,)] * 11)
    monkeypatch.setattr(tools, "get_read_conn", lambda: conn)
    result = tools.run_sql("SELECT total_amount AS revenue FROM sales.orders")
    assert result["status"] == "SUCCESS" and len(result["rows"]) == 20 and result["truncated"]
    assert result["rows"][0] == ["2351.05"] and result["rows"][1] == [None]
    assert "LIMIT 21" in conn.executed[0][0] and conn.closed


def test_rejection_never_connects(monkeypatch):
    monkeypatch.setattr(tools, "get_read_conn", lambda: pytest.fail("Database must not be contacted"))
    assert tools.run_sql("DROP TABLE sales.orders")["status"] == "POLICY_REJECTION"


@pytest.mark.parametrize(
    "rows,columns",
    [
        ([("x" * 2049,)], ("long",)),
        ([tuple("x" for _ in range(33))], tuple("c" + str(i) for i in range(33))),
        ([("a", "b")], ("duplicate", "duplicate")),
    ],
)
def test_large_or_ambiguous_results_rejected(monkeypatch, rows, columns):
    monkeypatch.setattr(tools, "get_read_conn", lambda: Connection(rows, columns))
    assert tools.run_sql("SELECT * FROM sales.orders")["error_code"] == "RESULT_BOUND"


def test_database_error_sanitized(monkeypatch):
    monkeypatch.setattr(tools, "get_read_conn", lambda: Connection(error=RuntimeError("SECRET_SENTINEL")))
    result = tools.run_sql("SELECT * FROM sales.orders")
    assert result["status"] == "DATABASE_ERROR" and "SECRET_SENTINEL" not in str(result)


def test_statement_timeout_category(monkeypatch):
    exc = RuntimeError("private SQL")
    exc.sqlstate = "57014"
    monkeypatch.setattr(tools, "get_read_conn", lambda: Connection(error=exc))
    assert tools.run_sql("SELECT * FROM sales.orders")["status"] == "TIMEOUT"


def test_read_only_configuration_with_fake_connector(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "synthetic-test-config")
    called = []
    conn = Connection()
    result = db._connect(read_only=True, connector=lambda *a, **kw: called.append(kw) or conn)
    assert result.read_only is True and called[0]["connect_timeout"] == 5
    assert "statement_timeout=5000" in called[0]["options"]
    assert "pg_catalog,public" in called[0]["options"]


def test_unapproved_metadata_table_does_not_connect(monkeypatch):
    monkeypatch.setattr(tools, "get_read_conn", lambda: pytest.fail("Must not connect"))
    assert tools.get_schema("evil.orders")["status"] == "INVALID_REQUEST"


def test_foreign_key_target_schema_preserved(monkeypatch):
    queries = []

    def read(query, params=()):
        queries.append((query, params))
        if "information_schema.columns" in query:
            return [("customer_id", "integer", "YES")]
        return [("customer_id", "sales", "customers", "id")]

    monkeypatch.setattr(tools, "_read", read)
    result = tools.get_schema("sales.orders")
    assert result["foreign_keys"] == [
        {"column": "customer_id", "references_table": "sales.customers", "references_column": "id"}
    ]
    assert queries[0][1] == ("orders",)


class Embedder:
    def __init__(self):
        self.texts = []

    def encode(self, text):
        self.texts.append(text)
        return [1.0] + [0.0] * 383


def test_retrieval_metadata_and_explicit_relation():
    conn = Connection([("doc_orders_total", "column", "total_amount", "Revenue guidance", 0.92, "sales.orders")])
    machine = Embedder()
    hits = schema_store.search_docs("delivered revenue", k=3, embedder=machine, connection_factory=lambda: conn)
    assert hits == [
        {
            "id": "doc_orders_total",
            "kind": "column",
            "name": "total_amount",
            "description": "Revenue guidance",
            "similarity": 0.92,
            "table": "sales.orders",
        }
    ]
    assert "FROM sales.schema_cards" in conn.executed[0][0] and conn.executed[0][1][-1] == 3


def test_loader_preserves_metadata_without_legacy_table(tmp_path):
    path = tmp_path / "cards.jsonl"
    path.write_text(
        json.dumps(
            {"id": "doc_x", "kind": "column", "name": "total", "table": "sales.orders", "description": "Guidance"}
        )
        + "\n"
    )
    conn = Connection()
    machine = Embedder()
    assert schema_store.load_docs(path=path, embedder=machine, connection_factory=lambda: conn) == 1
    assert "sales.schema_cards" in conn.executed[0][0] and conn.executed[0][1][3] == "sales.orders"


def test_duplicate_cards_fail_before_db(tmp_path):
    path = tmp_path / "cards.jsonl"
    path.write_text((json.dumps({"id": "same", "description": "Guidance"}) + "\n") * 2)
    with pytest.raises(ValueError):
        schema_store.load_docs(path=path, embedder=Embedder(), connection_factory=lambda: pytest.fail("No DB"))


@pytest.mark.parametrize("k", [0, 11, True])
def test_retrieval_bounds(k):
    with pytest.raises(ValueError):
        schema_store.search_docs("revenue", k=k, embedder=Embedder(), connection_factory=lambda: pytest.fail("No DB"))


def test_public_corpus_baseline():
    cards = schema_store.read_cards()
    by_id = {c["id"]: c for c in cards}
    assert len(cards) == 12 and "SUM(total_amount)" in by_id["doc_orders_total"]["description"]
    assert "status = 'delivered'" in by_id["doc_orders_status"]["description"]
    assert "orders.customer_id = customers.id" in by_id["doc_join_orders_customers"]["description"]


def test_empty_rows_distinct_from_null():
    obs = SQLObservation("sql_1", "SELECT", ("revenue",), ())
    result = render_database_answer('{"evidence_id":"sql_1","row_indices":[]}', {"sql_1": obs})
    assert result.status == Status.NO_DATA
    obs = SQLObservation("sql_1", "SELECT", ("revenue",), ((None,),))
    result = render_database_answer('{"evidence_id":"sql_1","row_indices":[0]}', {"sql_1": obs})
    assert "not a measured zero" in result.answer_text


def test_high_similarity_is_not_business_evidence(tmp_path):
    from test_runtime import response, service

    a, c = service(
        tmp_path,
        [response(calls=[("search_schema", {"query": "revenue"})]), response("Revenue is 2351.05")],
        {"search_schema": lambda query: [{"id": "doc_orders_total", "description": "Use SUM", "similarity": 1.0}]},
    )
    assert a.answer("Revenue?").status == Status.POLICY_REJECTION


def test_total_result_byte_cap(monkeypatch):
    monkeypatch.setattr(
        tools, "get_read_conn", lambda: Connection([tuple("x" * 1024 for _ in range(4))] * 20, ("a", "b", "c", "d"))
    )
    assert tools.run_sql("SELECT * FROM sales.orders")["error_code"] == "RESULT_BOUND"


@pytest.mark.parametrize("values", [[1.0] * 383, [float("nan")] + [1.0] * 383, [0.0] * 384])
def test_bad_embedding_rejected_before_read_connection(values):
    machine = NS(encode=lambda text: values)
    with pytest.raises(ValueError):
        schema_store.search_docs(
            "revenue", embedder=machine, connection_factory=lambda: pytest.fail("No database read")
        )


def test_pooling_is_invariant_to_masked_padding():
    import numpy as np
    from sales_agent.embedder import OnnxEmbedder

    machine = OnnxEmbedder.__new__(OnnxEmbedder)
    machine.tokenizer = NS(encode=lambda text: NS(ids=[1, 2, 0], attention_mask=[1, 1, 0], type_ids=[0, 0, 0]))
    hidden = np.ones((1, 3, 384))
    hidden[0, 2, :] = np.arange(384) * 100
    machine.session = NS(run=lambda *args: [hidden])
    first = machine.encode("Fixture")
    hidden[0, 2, :] = -np.arange(384) * 100
    second = machine.encode("Fixture")
    assert np.allclose(first, second) and first.shape == (384,) and np.isclose(np.linalg.norm(first), 1)
