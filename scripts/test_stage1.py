"""Automated sanity assertions for Stage 1: Embedder + pgvector store."""
import numpy as np
from sales_agent.embedder import OnnxEmbedder
from sales_agent.schema_store import init_store, load_docs, search_docs

def test_embedder():
    print("Testing ONNX Embedder...")
    emb = OnnxEmbedder()
    vec = emb.encode("test query")
    assert isinstance(vec, np.ndarray), "Output must be a numpy array"
    assert vec.shape == (384,), f"Expected shape (384,), got {vec.shape}"
    norm = float(np.linalg.norm(vec))
    assert abs(norm - 1.0) < 1e-4, f"Vector must be L2-normalized to 1.0, got {norm}"
    print("  ✓ Embedder output shape (384,) and L2 norm verified.")

def test_pgvector_store():
    print("Testing pgvector Store...")
    init_store()
    count = load_docs()
    assert count == 12, f"Expected 12 cards upserted, got {count}"
    
    hits = search_docs("revenue by region", k=3)
    assert len(hits) == 3, f"Expected 3 hits, got {len(hits)}"
    for hit in hits:
        assert "id" in hit and "similarity" in hit, "Hit missing required fields"
        assert -1.0 <= hit["similarity"] <= 1.0, f"Similarity out of bounds: {hit['similarity']}"
    print(f"  ✓ pgvector loaded {count} cards and executed top-k cosine search.")

if __name__ == "__main__":
    test_embedder()
    test_pgvector_store()
    print("\nStage 1 All Checks Passed.")
