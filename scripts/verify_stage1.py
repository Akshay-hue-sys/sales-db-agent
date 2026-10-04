import json
from pathlib import Path
from sales_agent.schema_store import init_store, load_docs, search_docs


def main():
    # Ensure store and index exist, then upsert documentation cards
    init_store()
    print(f"Loaded {load_docs()} cards\n")

    cases = json.loads((Path(__file__).resolve().parents[1] / "evals" / "retrieval_cases.json").read_text())
    for case in cases:
        q = case["query"]
        print(f"Query: '{q}'")
        hits = search_docs(q, k=3)
        assert set(case["expected_any"]) & {hit["id"] for hit in hits}, "Expected guidance missing from top 3"
        for hit in hits:
            # Format: similarity score, doc identifier, truncated description
            print(f"  [{hit['similarity']:.3f}] {hit['id']:<26} {hit['description'][:70]}")
        print()


if __name__ == "__main__":
    main()
