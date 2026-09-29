# Autonomous Sales Database Agent

A production-grade, multi-provider ReAct agent that translates natural language business inquiries into safe, verified SQL queries over PostgreSQL using semantic schema discovery, AST-level query guardrails, and dynamic model routing.

---

## Architecture & Technology Stack

- **Runtime Environment:** Python 3.12+ managed with `uv`.
- **Orchestration Layer:** ReAct loop powered by `litellm` with dynamic provider discovery (`gemini-3.5-flash-lite`, `gpt-4o-mini`, `claude-3-5-haiku`).
- **Relational Data Store:** PostgreSQL 16 enforcing relational integrity (`sales.customers`, `sales.products`, `sales.orders`).
- **Semantic Layer & Vector Index:** `pgvector` with HNSW cosine indexing (`vector_cosine_ops`) over business schema documentation.
- **Embedding Pipeline:** Local CPU-optimized ONNX inference (`Xenova/all-MiniLM-L6-v2`) generating 384-dimensional normalized embeddings.
- **Execution Guardrails:** Strict read-only transaction tripwires, AST mutation blocking via `sqlglot` (`INSERT`, `UPDATE`, `DROP`, `ALTER`), and mandatory result set capping (`LIMIT 20`).

---

## Project Structure

```text
├── data/
│   ├── schema_docs.jsonl      # Schema documentation cards
│   └── seed.sql               # Base relational seed data
├── models/                    # Local ONNX model weights
├── scripts/
│   ├── download_model.py      # ONNX weights fetcher
│   ├── seed_database.py       # Idempotent DDL & data bootstrapper
│   └── verify_stage3.py       # End-to-end evaluation harness
├── src/
│   └── sales_agent/
│       ├── agent.py           # Core ReAct reasoning engine
│       ├── app.py             # Streamlit analytics dashboard
│       ├── gateway.py         # Multi-provider model discovery
│       └── tools.py           # Introspection, pgvector search & safe SQL executor
├── pyproject.toml             # Project manifest and dependencies
└── .env.example               # Environment variable templates



Quickstart (Clone & Run)
1. Prerequisites
Ensure you have the following installed:

uv (Fast Python package manager)

PostgreSQL 16+ with the pgvector extension enabled

2. Environment Configuration
Clone the repository and copy the environment template:

Bash
cp .env.example .env
Configure your .env file:

Code snippet
DATABASE_URL=postgresql://<user>:<password>@localhost:5432/<dbname>
GEMINI_API_KEY=your_gemini_api_key_here
(Optional: Provide OPENAI_API_KEY or ANTHROPIC_API_KEY to switch providers dynamically).

3. Dependency Installation & Database Setup
Install the locked dependencies and provision the database:

Bash
# Install virtual environment and packages
uv sync

# Idempotently provision schema, tables, seed data, and vector definitions
uv run python scripts/seed_database.py


4. Automated Verification Suite
Run the regression harness to verify database connectivity, tool calling, and ground-truth reasoning:

Bash
uv run python scripts/verify_stage3.py
Expected output:

Plaintext
[PASS] Agent successfully reasoned, queried SQL, and verified ground truth (2351.05).
5. Launch the Interactive Dashboard
Start the local Streamlit application:

Bash
uv run streamlit run src/sales_agent/app.py
Open your browser at http://localhost:8501 to test conversational SQL generation.