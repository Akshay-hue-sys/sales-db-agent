from sales_agent.schema_store import init_store, load_docs, search_docs

# Ensure store and index exist, then upsert documentation cards
init_store()
print(f"Loaded {load_docs()} cards\n")

queries = [
    "revenue by region",
    "average order value",
    "cancelled orders last quarter",
    "which products are Hardware",
    "customer signup growth by month",
]

for q in queries:
    print(f"Query: '{q}'")
    for hit in search_docs(q, k=3):
        # Format: similarity score, doc identifier, truncated description
        print(f"  [{hit['similarity']:.3f}] {hit['id']:<26} {hit['description'][:70]}")
    print()
