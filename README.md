# ⚡ Autonomous Sales Database Agent & Observability Engine

A production-grade, autonomous SQL reasoning agent built with PostgreSQL, vector-based schema discovery, deterministic execution safeguards, an append-only DuckDB telemetry pipeline, and an automated LLM evaluation harness.

---

## 🏛️ System Architecture

                         +------------------------+
                         |     User Question      |
                         +-----------+------------+
                                     |
                                     v
                         +------------------------+
                         |   SalesAgent (ReAct)   | <---+ Multi-Model Fallback Chain
                         | (gemini-flash-latest / |     | (Transient 503/429 Failover)
                         |  gemini-flash-lite)    |
                         +-----------+------------+
                                     |
             +-----------------------+-----------------------+
             |                       |                       |
             v                       v                       v
 +-----------------------+ +-------------------+ +-----------------------+
 |     search_schema     | |  describe_table   | |        run_sql        |
 | (pgvector / HNSW TopK)| | (PostgreSQL DDL)  | | (Read-Only Trx Guard) |
 +-----------------------+ +-------------------+ +-----------------------+
             |                       |                       |
             +-----------------------+-----------------------+
                                     |
                                     v
                         +------------------------+
                         |  Structured Telemetry  |
                         | (traces/log_records)   |
                         +-----------+------------+
                                     |
                                     v (dlt ELT Pipeline)
                         +------------------------+
                         | DuckDB Columnar Store  |
                         | (sales-db-agent.duckdb)|
                         +-----------+------------+
                                     |
                    +----------------+----------------+
                    |                                 |
                    v                                 v
      +---------------------------+     +---------------------------+
      |      Marimo Console       |     |    Scientific Evals       |
      |  (Reactive DAG Analytics) |     |  (L1 Regex + L2 Judge)    |
      +---------------------------+     +---------------------------+

---

## 🛡️ Architectural Invariants & Safety Tripwires

To prevent unpredictable agent execution, cost overruns, and database corruption, the runtime enforces the following guardrails:

1. **Deterministic Execution Limits:**
   - **Step Limit:** Hard cap of 6 reasoning iterations per query to prevent infinite ReAct loops.
   - **Token Budget:** 15,000 cumulative token safety tripwire across a session.
   - **Loop Detection:** Prohibits consecutive identical tool invocations with identical parameters.
2. **Transactional Database Safety:**
   - Database operations execute under strict read-only transactions (`SET TRANSACTION READ ONLY`) to prevent data mutation (`UPDATE`, `DELETE`, `DROP`).
3. **High-Availability Fallback Chain:**
   - Dynamic client failover from primary reasoning models to fallback models (`gemini-flash-latest` $\rightarrow$ `gemini-flash-lite-latest`) to mitigate transient upstream API rate limits or service unavailability.

---

## 🚀 Quickstart

### Prerequisites
- **macOS** or **Linux**
- **Python 3.12+** (configured with [`uv`](https://github.com/astral-sh/uv))
- **PostgreSQL 16+** with the `pgvector` extension enabled
- **Google Gemini API Key**

### 1. Clone & Set Up Virtual Environment
```bash
git clone [https://github.com/Akshay-hue-sys/sales-db-agent.git](https://github.com/Akshay-hue-sys/sales-db-agent.git)
cd sales-db-agent

# Install locked dependencies via uv
uv sync
2. Configure Environment Variables
Create a .env file in the root directory:

Code snippet
GEMINI_API_KEY="your-gemini-api-key"
DATABASE_URL="postgresql://user:password@localhost:5432/sales"
3. Initialize & Seed Database Schema
Embed database metadata into pgvector and seed baseline analytical records:

Bash
uv run python scripts/seed_database.py
💻 CLI Usage
Invoke the autonomous reasoning agent directly from the terminal:

Bash
uv run python -m sales_agent.cli "What is the total revenue of delivered orders?"
Sample agent execution flow:

Plaintext
[Thought] Need to find tables related to orders and revenue.
[Action]  search_schema(query='revenue orders')
[Action]  describe_table(table_name='sales.orders')
[Action]  run_sql(sql="SELECT SUM(total_amount) AS total_revenue FROM sales.orders WHERE status = 'delivered';")
[Final]   The total revenue of delivered orders is $2,351.05.
🔬 Scientific Evaluation Harness (Evals)
The system includes a two-tier evaluation framework:

L1 Deterministic Extraction: Regex and heuristic matching for expected scalars, entities, and out-of-scope refusal signals.

L2 Semantic Judge: An independent LLM-as-a-Judge (gemini-flash-lite-latest) scoring output accuracy, grounding, and reasoning on a 1–5 scale.

Run the test suite across all benchmark tiers:

Bash
uv run python -m evals.runner
Benchmark Baseline
Plaintext
=======================================================
           BENCHMARK EVALUATION SUMMARY           
=======================================================
Total Test Cases      : 4
L1 Deterministic Pass : 4/4 (100.0%)
Average Judge Score   : 5.00 / 5.0
Average Turn Latency  : ~5.27s
=======================================================
📊 Observability & Telemetry Pipeline
All agent actions, tool parameters, responses, and token expenditures are appended to traces/log_records.jsonl.

1. Ingest Traces via dlt into DuckDB
Transform unstructured telemetry logs into columnar relational vectors:

Bash
uv run python -m sales_agent.ingest
2. Inspect Ingestion Metrics
Verify loaded trace events and tool distribution directly in DuckDB:

Bash
uv run python scripts/verify_stage5.py
3. Launch Reactive Dashboard
Launch the interactive Marimo developer interface to analyze session paths, token consumption profiles, and tool distributions:

Bash
uv run marimo edit dashboard/traces_app.py
📂 Project Structure
Plaintext
sales-db-agent/
├── dashboard/
│   └── traces_app.py         # Reactive Marimo + Altair observability UI
├── evals/
│   ├── evaluator.py          # L1 deterministic checks & L2 LLM-as-a-Judge
│   ├── runner.py             # Evaluation harness runner & reporting
│   ├── test_suite.json       # Tiered benchmark evaluation cases
│   └── results.json          # Serialized benchmark run results
├── scripts/
│   ├── seed_database.py      # PostgreSQL schema creation & pgvector seeding
│   ├── seed_more_data.py     # Idempotent expansion seeder for analytical scale
│   ├── verify_stage2.py      # Database connectivity & vector index verification
│   ├── verify_stage3.py      # Agent loop & tool execution tests
│   └── verify_stage5.py      # Columnar DuckDB trace analytics verification
├── src/
│   └── sales_agent/
│       ├── agent.py          # ReAct reasoning loop with safety tripwires
│       ├── cli.py            # CLI entry point for interactive user queries
│       ├── db.py             # PostgreSQL connection lifecycle
│       ├── ingest.py         # dlt pipeline loading JSONL traces to DuckDB
│       ├── tools.py          # Schema search, DDL reflection, and SQL tools
│       └── trace.py          # Structured JSONL telemetry logger
├── pyproject.toml            # Project dependencies and environment metadata
└── README.md                 # System architecture and technical specifications
