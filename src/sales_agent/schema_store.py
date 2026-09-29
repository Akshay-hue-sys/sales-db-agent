"""Semantic schema search: doc cards -> pgvector -> HNSW -> top-k lookup."""
import json
import os
from pathlib import Path
import psycopg
from dotenv import load_dotenv

# Absolute package import to support script executions
from sales_agent.embedder import OnnxEmbedder

load_dotenv()

# Resolve absolute path to data/schema_docs.jsonl
DOCS_PATH = Path(__file__).resolve().parents[2] / "data" / "schema_docs.jsonl"
embedder = OnnxEmbedder()

def _conn() -> psycopg.Connection:
    """Establish connection using DATABASE_URL from .env."""
    return psycopg.connect(os.environ["DATABASE_URL"])

def init_store() -> None:
    """Create pgvector extension, table, and HNSW index if they do not exist."""
    with _conn() as conn:
        conn.execute("CREATE EXTENSION IF NOT EXISTS vector;")
        conn.execute("""
            CREATE TABLE IF NOT EXISTS schema_docs (
                id TEXT PRIMARY KEY,
                kind TEXT,
                name TEXT,
                description TEXT NOT NULL,
                embedding vector(384) NOT NULL
            );
        """)
        # HNSW cosine index for logarithmic approximate nearest neighbors
        conn.execute("""
            CREATE INDEX IF NOT EXISTS schema_docs_hnsw
            ON schema_docs USING hnsw (embedding vector_cosine_ops);
        """)
        conn.commit()

def load_docs() -> int:
    """Read schema cards, compute embeddings, and idempotently upsert into pgvector."""
    count = 0
    with _conn() as conn:
        for line in DOCS_PATH.read_text().splitlines():
            if not line.strip():
                continue
            doc = json.loads(line)
            vector = embedder.encode(doc["description"]).tolist()
            
            # Idempotent upsert via ON CONFLICT
            conn.execute("""
                INSERT INTO schema_docs (id, kind, name, description, embedding)
                VALUES (%s, %s, %s, %s, %s::vector)
                ON CONFLICT (id) DO UPDATE SET
                    kind = EXCLUDED.kind,
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    embedding = EXCLUDED.embedding;
            """, (doc["id"], doc.get("kind"), doc.get("name"), doc["description"], str(vector)))
            count += 1
        conn.commit()
    return count

def search_docs(query: str, k: int = 5) -> list[dict]:
    """Semantic search over schema cards using cosine distance (<=>)."""
    qv = str(embedder.encode(query).tolist())
    with _conn() as conn:
        # Distance operator <=> returns cosine distance (0 to 2 for normalized vectors)
        # Similarity = 1 - distance
        rows = conn.execute("""
            SELECT id, kind, name, description, 1 - (embedding <=> %s::vector) AS similarity
            FROM schema_docs
            ORDER BY embedding <=> %s::vector
            LIMIT %s;
        """, (qv, qv, k)).fetchall()
        
    return [
        {
            "id": r[0],
            "kind": r[1],
            "name": r[2],
            "description": r[3],
            "similarity": round(float(r[4]), 4)
        }
        for r in rows
    ]
