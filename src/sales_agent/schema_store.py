"""One explicit retrieval relation; legacy schema_docs tables remain untouched."""

import json
import math
from pathlib import Path

from sales_agent.db import get_conn, get_read_conn

DOCS_PATH = Path(__file__).resolve().parents[2] / "data" / "schema_docs.jsonl"
STORE_TABLE = "sales.schema_cards"
STORE_DDL = """
CREATE EXTENSION IF NOT EXISTS vector WITH SCHEMA public;
CREATE SCHEMA IF NOT EXISTS sales;
CREATE TABLE IF NOT EXISTS sales.schema_cards (
    id TEXT PRIMARY KEY, kind TEXT, name TEXT, table_name TEXT,
    description TEXT NOT NULL, embedding vector(384) NOT NULL
);
CREATE INDEX IF NOT EXISTS schema_cards_hnsw
ON sales.schema_cards USING hnsw (embedding vector_cosine_ops);
"""
_embedder = None


def get_embedder():
    global _embedder
    if _embedder is None:
        from sales_agent.embedder import OnnxEmbedder

        _embedder = OnnxEmbedder()
    return _embedder


def _vector(text, embedder):
    values = list(embedder.encode(text))
    if len(values) != 384 or not all(math.isfinite(float(x)) for x in values):
        raise ValueError("Invalid embedding shape or values.")
    if not any(values):
        raise ValueError("Zero embedding is not usable for cosine retrieval.")
    return str([float(x) for x in values])


def read_cards(path=DOCS_PATH):
    cards = [json.loads(line) for line in Path(path).read_text().splitlines() if line.strip()]
    seen = set()
    for card in cards:
        if (
            not isinstance(card.get("id"), str)
            or not isinstance(card.get("description"), str)
            or not card["description"].strip()
            or card["id"] in seen
        ):
            raise ValueError("Invalid or duplicate schema card.")
        seen.add(card["id"])
    return cards


def init_store(*, connection_factory=None):
    with (connection_factory or get_conn)() as conn:
        conn.execute(STORE_DDL)


def load_docs(*, path=DOCS_PATH, embedder=None, connection_factory=None):
    cards = read_cards(path)
    machine = embedder if embedder is not None else get_embedder()
    prepared = [(c, _vector(c["description"], machine)) for c in cards]
    with (connection_factory or get_conn)() as conn:
        for card, vector in prepared:
            conn.execute(
                """INSERT INTO sales.schema_cards (id,kind,name,table_name,description,embedding)
                VALUES (%s,%s,%s,%s,%s,%s::vector) ON CONFLICT (id) DO UPDATE SET
                kind=EXCLUDED.kind, name=EXCLUDED.name, table_name=EXCLUDED.table_name,
                description=EXCLUDED.description, embedding=EXCLUDED.embedding""",
                (card["id"], card.get("kind"), card.get("name"), card.get("table"), card["description"], vector),
            )
    return len(cards)


def search_docs(query, k=5, *, embedder=None, connection_factory=None):
    if not isinstance(query, str) or not query.strip() or len(query) > 1000 or type(k) is not int or not 1 <= k <= 10:
        raise ValueError("Invalid retrieval query or result bound.")
    vector = _vector(query, embedder if embedder is not None else get_embedder())
    with (connection_factory or get_read_conn)() as conn:
        rows = conn.execute(
            """SELECT id,kind,name,description,1-(embedding <=> %s::vector),table_name
            FROM sales.schema_cards ORDER BY embedding <=> %s::vector, id LIMIT %s""",
            (vector, vector, k),
        ).fetchall()
    return [
        {
            "id": r[0],
            "kind": r[1],
            "name": r[2],
            "description": r[3],
            "similarity": round(float(r[4]), 4),
            "table": r[5],
        }
        for r in rows
    ]
