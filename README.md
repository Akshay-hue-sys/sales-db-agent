# Sales DB Agent

A simple AI assistant for asking questions about sales data in normal English.

You can ask something like:

> What is the total revenue from delivered orders?

The system uses **Gemini** to decide what information it needs, but Gemini does **not** directly control the database. Python checks and runs approved tools, and **PostgreSQL** provides the real sales facts.

This is a portfolio project with safety checks and offline tests. It is not a claim of perfect text-to-SQL accuracy or full production readiness.

---

## How the project works

```text
User question
    ↓
SalesAgent
    ↓
Gemini decides which tool it needs
    ↓
Python checks the tool request
    ↓
Approved tool runs
    ↓
PostgreSQL returns real data
    ↓
Python stores the result as evidence
    ↓
Gemini selects the evidence it wants to use
    ↓
Python checks the evidence and shows the final answer
```

The most important rule is:

> **Gemini plans. Python controls. PostgreSQL provides the business facts.**

RAG helps Gemini understand the database, but RAG does not calculate sales numbers.

---

## Main parts of the system

### 1. SalesAgent — the manager

`SalesAgent` controls the full agent loop.

It sends the question to Gemini, receives tool requests, checks those requests, runs approved tools, and gives the results back to Gemini.

The project has one main agent loop so the CLI, Streamlit UI, and evaluations all use the same logic.

Important files:

- `src/sales_agent/agent.py`
- `src/sales_agent/config.py`

---

### 2. Gemini — the planner

Gemini tries to understand the user question and decides which tool it needs.

For example, it may decide:

```text
I need to know which sales tables exist.
```

or:

```text
I need to run a SQL query to calculate revenue.
```

Gemini only **requests** tools. Python decides whether the request is valid and allowed.

---

## The five approved tools

| Tool | Simple purpose |
|---|---|
| `get_schema` | Shows approved sales tables, columns, and relationships |
| `list_tables` | Lists approved sales tables/views |
| `describe_table` | Shows the columns of one approved table |
| `search_schema` | Finds useful schema/business guidance using RAG |
| `run_sql` | Runs one approved analytical SQL query |

The main business tables are:

- `sales.customers`
- `sales.products`
- `sales.orders`

Unknown tools, bad arguments, and duplicate tool requests are rejected instead of being executed.

Important file:

- `src/sales_agent/tools.py`

---

## Example: asking for delivered revenue

Question:

> What is the total revenue from delivered orders?

Gemini may request SQL like this:

```sql
SELECT SUM(total_amount) AS revenue
FROM sales.orders
WHERE status = 'delivered';
```

Python checks the SQL before it reaches PostgreSQL.

If the query is allowed, PostgreSQL runs it and returns the real result.

The project then stores that result as evidence, for example:

```text
evidence_id = sql_1
```

Gemini does not freely rewrite the business number. Instead, it selects the evidence and row it wants to use:

```json
{"evidence_id":"sql_1","row_indices":[0]}
```

Python checks that the evidence really exists and then renders the observed database value.

This reduces the chance of Gemini inventing numbers.

Important files:

- `src/sales_agent/contracts.py`
- `src/sales_agent/agent.py`

---

## What “evidence” means in this project

Think of evidence as a **receipt**.

If Gemini thinks the answer is `5000`, that is not enough.

If PostgreSQL actually returns `2351.05`, that database result is the evidence.

```text
Gemini guess
    ✗ not evidence

RAG similarity score
    ✗ not evidence

Schema card
    ✗ not business evidence

Executed PostgreSQL result
    ✓ business evidence
```

The project keeps SQL observations during the current run and uses evidence IDs to connect the final answer to the real database result.

Important limitation:

> Evidence proves where the number came from. It does not prove that the SQL query itself was the perfect interpretation of the user question.

For example, a SQL query may run correctly but still use the wrong filter or join.

---

## RAG in this project

RAG is used only to help Gemini understand the database structure and business meaning.

The project contains 12 public schema/business guidance cards.

The flow is:

```text
Schema/business cards
    ↓
Local embedding model
    ↓
384-number vectors
    ↓
pgvector in PostgreSQL
    ↓
Find similar cards
    ↓
Give helpful guidance to Gemini
```

Example:

A user asks about **revenue**.

RAG may find a card explaining that `total_amount` is the important field and that `delivered` is a useful status filter.

RAG does **not** return the current revenue number.

```text
RAG = guidance
SQL + PostgreSQL = actual business facts
```

Important files:

- `src/sales_agent/schema_store.py`
- `src/sales_agent/embedder.py`
- `data/schema_docs.jsonl`

The canonical vector table is:

```text
sales.schema_cards
```

---

## Local embeddings

The project uses a local ONNX embedding model for schema RAG.

This means the small embedding step does not need a cloud embedding API.

The local model converts text into a 384-number vector. pgvector then compares those vectors to find similar guidance cards.

Benefits:

- no embedding API call
- useful for the small schema corpus
- keeps vector search close to PostgreSQL

Trade-off:

- local model files must be available
- retrieval quality still needs to be measured
- a high similarity score does not mean the information is true

---

## PostgreSQL vs DuckDB

These databases have different jobs.

### PostgreSQL

PostgreSQL is the source of business facts.

It stores:

- customers
- products
- orders
- schema guidance vectors

It answers questions such as:

> What is the revenue from delivered orders?

### DuckDB

DuckDB is used for trace/history analytics.

It helps answer questions such as:

> What happened during an agent run?

or:

> Which tools were used and how long did they take?

**DuckDB is not the sales source of truth in the current architecture.**

---

## SQL safety

Gemini can generate SQL, so the application checks it before execution.

The SQL safety layer uses SQLGlot to parse the query.

The runtime rejects things such as:

- writes
- multiple SQL statements
- unapproved tables
- unsafe functions
- locking queries
- unsupported query shapes

The normal agent database connection is read-only.

The system also uses limits such as:

- 5-second SQL statement timeout
- 2-second lock timeout
- 5-second connection timeout
- maximum 20 result rows
- maximum 32 columns
- cell and total-result size limits

These controls reduce risk, but they are not a perfect SQL sandbox. A least-privilege PostgreSQL role is still important.

Important files:

- `src/sales_agent/sql_policy.py`
- `src/sales_agent/db.py`
- `src/sales_agent/tools.py`

---

## Agent limits

The agent is not allowed to run forever.

The default configuration includes limits such as:

- maximum model turns
- maximum tool calls per turn
- maximum elapsed time
- maximum reported token usage

These limits help stop runaway loops and unnecessary API usage.

---

## Gemini model behavior

Gemini is initialized only when it is actually needed.

The project can inspect the available Gemini model catalog and choose an allowed candidate when no model is explicitly configured.

Important behavior:

- authentication errors are not treated as temporary
- permission errors are not blindly retried
- quota errors such as `429` remain quota errors
- temporary provider/server failures may receive a few same-model retries

The project does not blindly jump between models when quota is exhausted.

Important file:

- `src/sales_agent/models.py`

---

## Privacy-friendly tracing

The project records safe metadata about agent runs.

Example event types include:

- user event
- model request
- tool use
- tool result status
- token usage
- assistant event
- session end

The current trace format does **not** store normal private payloads such as:

- full user questions
- SQL text
- database rows
- prompts
- final answers
- credentials
- environment values

The flow is:

```text
SalesAgent
    ↓
TraceLogger
    ↓
JSONL metadata
    ↓
manual dlt ingestion
    ↓
DuckDB
    ↓
dashboard / analysis
```

Important files:

- `src/sales_agent/trace.py`
- `src/sales_agent/ingest.py`
- `dashboard/traces_app.py`

Repeated append ingestion can duplicate old events, so ingestion is still an area that can be improved.

---

## Installation

Requirements:

- Python 3.14+
- PostgreSQL
- pgvector
- Gemini API access for live agent use
- local embedding assets only when RAG is used

Install the locked dependencies:

```bash
uv sync --locked
```

The application expects private environment variables such as:

```text
DATABASE_URL
GEMINI_API_KEY
```

Optional:

```text
GEMINI_MODEL
```

Do not commit real secret values to GitHub.

The current application does not automatically load `.env` files.

---

## Running the CLI

Examples:

```bash
PYTHONPATH=src .venv/bin/python cli.py
```

or:

```bash
PYTHONPATH=src .venv/bin/python -m sales_agent.cli \
  "What is the total revenue from delivered orders?"
```

Installed command names also include:

```bash
sales-agent
sales-db-agent
```

These are **live commands**. They may call Gemini, read PostgreSQL, and write trace metadata.

---

## Optional Streamlit UI

Run:

```bash
PYTHONPATH=src .venv/bin/streamlit run src/sales_agent/app.py
```

The Streamlit UI uses the same `SalesAgent` logic as the CLI.

Displayed chat history is only UI history. It is not currently passed back into the agent as persistent conversation memory.

---

## Safe offline tests

Run the offline suite with:

```bash
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python tests/run_offline.py
```

Optional lint check:

```bash
.venv/bin/ruff check src tests evals scripts cli.py dashboard
```

The offline test runner blocks access to:

- the real network
- real Gemini clients
- real PostgreSQL connections
- secret files
- dotenv loading
- production traces/databases
- real embedding assets

Tests use fake models, fake tools, fake database responses, and temporary files.

This lets the project test important Python behavior without spending API quota or touching real data.

Important reminder:

> Passing offline tests does not prove that Gemini, PostgreSQL, pgvector, or the UI are working correctly in a live environment.

---

## Live and maintenance operations

Some scripts are intentionally not part of the safe offline test path.

Examples:

- database seed scripts can write business data
- RAG setup can create/load `sales.schema_cards`
- model download scripts use the network
- some verification scripts call Gemini or PostgreSQL
- evaluation runs can write sensitive result files

Run those only when you know the side effects and intend to use the live services.

---

## Main project files

| File | Simple purpose |
|---|---|
| `agent.py` | Main agent loop and tool coordination |
| `tools.py` | Five approved tools |
| `contracts.py` | Evidence objects and final answer checks |
| `sql_policy.py` | SQL safety rules |
| `db.py` | PostgreSQL connections |
| `schema_store.py` | RAG card storage/search |
| `embedder.py` | Local embedding model |
| `models.py` | Gemini model setup and error handling |
| `config.py` | Agent limits and configuration |
| `trace.py` | Safe trace metadata |
| `ingest.py` | Loads traces into DuckDB |
| `cli.py` | Terminal interface |

Other notes:

- `gateway.py` is an older/unused multi-provider naming helper, not the active routing system.
- `mcp_server.py` is an optional manual server and is not part of the normal CLI flow.

---

## What is already implemented

The current project includes:

- one bounded Gemini agent loop
- five approved tools
- PostgreSQL business data access
- schema/business RAG
- local ONNX embeddings
- pgvector retrieval
- SQL AST validation
- read-only agent database connections
- evidence-based final answer rendering
- privacy-focused tracing
- DuckDB trace analytics
- offline tests with fake services
- CLI and optional Streamlit UI

---

## What is not fully proven yet

The project still has important limitations.

Examples:

- generated SQL may run correctly but still misunderstand the user's intent
- live PostgreSQL permissions still need proper integration validation
- RAG quality needs more measurement
- the model catalog does not prove a model supports every tool-calling use case
- Streamlit/live end-to-end behavior is not fully certified by offline tests
- trace ingestion can duplicate events when repeatedly appended
- there is no persistent conversation memory
- there is no multi-agent system
- there is no automatic deployment system
- there is no semantic SQL checker that proves the query matches the user's business meaning

These are current limitations, not hidden failures.

---

## Why this is an AI engineering project

This project demonstrates several practical AI engineering ideas:

- LLM agents
- function/tool calling
- RAG
- embeddings
- pgvector
- PostgreSQL
- text-to-SQL
- evidence grounding
- SQL safety
- deterministic Python controls
- observability
- offline testing
- evaluation boundaries
- privacy-aware logging

The important idea is that the LLM is only one part of the system.

```text
LLM planning
    ↓
controlled tools
    ↓
real database results
    ↓
evidence checks
    ↓
validated answer
```

---

## Good explanation

> I built a Gemini-based sales agent that lets users ask sales questions in normal English. Gemini decides which approved tool it needs, but Python validates and executes the tools. RAG helps the model understand the schema and business terms, while PostgreSQL provides the actual sales facts. Successful SQL results become evidence objects, and Python checks those evidence references before returning business values. I also added SQL safety, read-only database access, agent limits, privacy-focused tracing, DuckDB trace analytics, and offline tests with fake services.

---



## One sentence to remember

> **Gemini plans, Python controls, PostgreSQL provides the facts, RAG provides guidance, and DuckDB helps debug the agent.**
