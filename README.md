# Autonomous Sales Database Agent

> A production-minded Agentic AI system that dynamically explores a sales database, generates read-only SQL, executes queries against DuckDB, and returns grounded answers using a ReAct-style agent loop.

## Overview

The **Autonomous Sales Database Agent** is an Agentic AI and Data Engineering project designed to answer natural-language business questions using data stored in a local sales database.

Instead of placing an entire database schema inside an LLM prompt, the system gives the AI agent deterministic tools that allow it to:

1. discover available database tables,
2. inspect table schemas,
3. reason about the user's question,
4. generate SQL,
5. execute read-only queries,
6. inspect the returned data,
7. and synthesize a grounded natural-language answer.

The project also includes evaluation, safety tripwires, structured tracing, telemetry analytics, and an interactive command-line interface.

---

## Why This Project Exists

A basic text-to-SQL application often follows this pattern:

```text
User Question
      ↓
     LLM
      ↓
Generated SQL
      ↓
Database
```

That approach becomes brittle when:

- database schemas grow,
- schemas change,
- questions require multiple tables,
- SQL generation fails,
- the model hallucinates schema details,
- or there is no way to measure what the agent actually did.

This project instead uses a tool-driven agent architecture:

```text
                    ┌─────────────────┐
                    │      User       │
                    └────────┬────────┘
                             │
                             ▼
                    ┌─────────────────┐
                    │   ReAct Agent   │
                    │     Gemini      │
                    └────────┬────────┘
                             │
                    Reason → Act → Observe
                             │
                ┌────────────┼────────────┐
                │            │            │
                ▼            ▼            ▼
         ┌────────────┐ ┌──────────┐ ┌─────────┐
         │List Tables │ │Get Schema│ │ Run SQL │
         └────────────┘ └──────────┘ └────┬────┘
                                          │
                                          ▼
                                    ┌──────────┐
                                    │ DuckDB   │
                                    └──────────┘
```

The LLM performs reasoning and tool selection.

DuckDB remains the deterministic source of truth for business data.

---

# Core Engineering Principle

## Probabilistic AI + Deterministic Data

LLMs are probabilistic systems.

Databases are deterministic systems.

This project deliberately separates those responsibilities.

The LLM can decide:

```text
"I need total revenue by region."
```

It should **not invent or mentally calculate the result**.

Instead, it generates an appropriate query:

```sql
SELECT
    region,
    SUM(revenue) AS total_revenue
FROM sales
GROUP BY region;
```

DuckDB executes the calculation.

The actual rows are then returned to the agent, which converts the verified result into a human-readable answer.

```text
LLM Reasoning
      ↓
SQL Generation
      ↓
Deterministic DuckDB Execution
      ↓
Verified Data
      ↓
LLM Explanation
```

This deterministic boundary is one of the central architectural principles of the project.

---

# Architecture

The project is organized into five implemented architectural planes.

```text
┌───────────────────────────────────────────────┐
│                Interface Plane                │
│                    CLI                        │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────┐
│                 Compute Plane                 │
│             Gemini + ReAct Loop               │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
┌───────────────────────────────────────────────┐
│                 Tooling Plane                 │
│   list_tables │ get_schema │ run_sql          │
└──────────────────────┬────────────────────────┘
                       │
                       ▼
                 ┌────────────┐
                 │   DuckDB   │
                 └────────────┘


          ┌───────────────────────────┐
          │     Evaluation Plane      │
          │ L1 Deterministic + L2 LLM│
          └───────────────────────────┘

          ┌───────────────────────────┐
          │   Observability Plane     │
          │ JSONL → DuckDB Analytics │
          └───────────────────────────┘
```

---

# Project Stages

| Stage | Component | Status |
|---|---|---|
| Stage 0 | Project Origin & Environment Setup | ✅ Complete |
| Stage 1 | Tooling Plane — Database Introspection | ✅ Complete |
| Stage 2 | Compute Plane — ReAct Agent | ✅ Complete |
| Stage 3 | Evaluation Plane — L1/L2 Benchmarks | ✅ Complete |
| Stage 4 | Observability Plane — JSONL + DuckDB | ✅ Complete |
| Stage 5 | Interface Plane — Interactive CLI | ✅ Complete |
| Stage 6 | FastAPI REST Endpoint | 📋 Planned |

---

# Stage 0 — Project Setup

The project begins with a local Python development environment designed for reproducibility and safe secret management.

### Development Environment

- macOS
- VS Code
- Python 3.12+
- `uv`
- Gemini API
- DuckDB
- `.env` environment configuration

Secrets such as the Gemini API key are stored locally:

```text
.env
```

A public repository should instead provide:

```text
.env.example
```

The real `.env` must remain excluded through `.gitignore`.

> **Security:** Never commit API keys or other credentials to GitHub.

---

# Stage 1 — Tooling Plane

The first major engineering layer gives the agent controlled access to the database.

The primary tools are conceptually:

```python
list_tables()
get_schema()
run_sql()
```

### `list_tables`

Allows the agent to discover which tables exist.

### `get_schema`

Allows the agent to inspect table structure before attempting a query.

### `run_sql`

Executes SQL against DuckDB.

The SQL execution boundary is restricted to read-only operations.

This allows the agent to retrieve facts without being given unrestricted database modification privileges.

### Mental Model

Think of the database as a library.

Instead of memorizing the entire library catalogue inside the prompt, the agent receives:

```text
list_tables() → library directory

get_schema()  → inspect a bookshelf

run_sql()     → retrieve the requested information
```

---

# Stage 2 — Compute Plane

Stage 2 introduces the Agentic AI layer.

The system follows a ReAct-style pattern:

```text
Reason
  ↓
Act
  ↓
Observe
  ↓
Reason Again
```

A typical request might behave like this:

```text
User:
"What was total revenue by region?"

        ↓

Agent:
"I need to understand the database."

        ↓

list_tables()

        ↓

Agent:
"I need the sales table schema."

        ↓

get_schema(...)

        ↓

Agent:
"I can now construct the query."

        ↓

run_sql(...)

        ↓

DuckDB Result

        ↓

Agent:
Natural-language answer
```

The model therefore does not need to know the database structure beforehand.

It discovers what it needs during execution.

---

## Agent Safety Tripwires

Autonomous agents can accidentally loop.

The project therefore introduces execution limits including:

```python
MAX_STEPS = 8
MAX_SECONDS = 45
MAX_TOKENS = 30_000
```

These act as circuit breakers.

If the agent repeatedly calls tools or fails to converge, execution is terminated rather than consuming unlimited API resources.

---

## Model Fallback

The compute layer also includes model fallback behavior.

When API capacity or quota errors such as:

```text
429 RESOURCE_EXHAUSTED
```

occur, the system can retry and move through a fallback model strategy rather than immediately crashing.

---

# Stage 3 — Evaluation Plane

A working demo does not prove that an AI system is reliable.

Stage 3 therefore introduces an evaluation framework.

The evaluation system contains two layers.

## L1 — Deterministic Evaluation

Fast and inexpensive checks verify known properties of the response.

Examples include:

- expected numbers,
- expected strings,
- regex patterns,
- known empty-result behavior.

Conceptually:

```text
Agent Answer
     ↓
Deterministic Rules
     ↓
PASS / FAIL
```

These tests are fast and reproducible.

---

## L2 — LLM-as-a-Judge

Some answers may be semantically correct without exactly matching an expected string.

A second LLM-based evaluator can therefore judge response quality on a numerical scale.

```text
Agent Answer
     +
Expected Behaviour
     ↓
LLM Judge
     ↓
Quality Score
```

The two evaluation layers complement each other:

```text
L1
Fast
Cheap
Deterministic

        +

L2
Semantic
Flexible
Probabilistic
```

---

# Stage 4 — Observability Plane

An agent that cannot be observed is difficult to debug or improve.

Stage 4 introduces structured tracing.

The application writes structured events to:

```text
traces/log_records.jsonl
```

using a `TraceLogger`.

Conceptually:

```text
Agent Execution
      ↓
Structured Events
      ↓
log_records.jsonl
      ↓
Ingestion
      ↓
DuckDB
      ↓
Analytical Views
      ↓
Metrics
```

This makes it possible to analyze properties such as:

- execution latency,
- tool usage,
- session completion,
- token consumption,
- failures,
- model behavior.

The observability layer acts like an aircraft's black box: when something behaves unexpectedly, the execution history can be inspected rather than guessed.

---

# Stage 5 — Interactive CLI

The fifth implemented stage provides a human-facing interface.

The CLI captures user input and sends it to the agent:

```text
Terminal
   ↓
User Question
   ↓
run_agent()
   ↓
ReAct Loop
   ↓
DuckDB Tools
   ↓
Answer
   ↓
Terminal
```

This creates a lightweight environment for manually testing the complete system before introducing a web/API layer.

---

# Project Structure

The documented project structure is:

```text
sales-db-agent/
├── pyproject.toml
├── .env
├── .gitignore
├── cli.py
├── telemetry.duckdb
│
├── traces/
│   └── log_records.jsonl
│
├── evals/
│   ├── evaluator.py
│   ├── runner.py
│   └── test_suite.json
│
└── src/
    └── sales_agent/
        ├── agent.py
        ├── tools.py
        └── trace.py
```

### Major Components

| File | Responsibility |
|---|---|
| `agent.py` | ReAct agent execution loop |
| `tools.py` | Deterministic DuckDB tools |
| `trace.py` | Structured execution tracing |
| `cli.py` | Interactive terminal interface |
| `evaluator.py` | L1/L2 evaluation logic |
| `runner.py` | Evaluation execution harness |
| `test_suite.json` | Golden evaluation cases |
| `log_records.jsonl` | Raw structured telemetry |
| `telemetry.duckdb` | Analytical telemetry database |

---

# Technology Stack

| Technology | Purpose |
|---|---|
| Python | Application and agent logic |
| Gemini API | LLM reasoning and function/tool calling |
| DuckDB | Local analytical database |
| `google-genai` | Gemini API client |
| `uv` | Python project and dependency management |
| Pydantic | Structured validation |
| `python-dotenv` | Environment-variable loading |
| JSONL | Append-only structured telemetry |
| VS Code | Development environment |

---

# Installation

## 1. Clone the Repository

```bash
git clone <YOUR_REPOSITORY_URL>
cd sales-db-agent
```

If you are rebuilding the project manually:

```bash
mkdir sales-db-agent
cd sales-db-agent
```

---

## 2. Initialize the Python Project

```bash
uv init
```

---

## 3. Install Dependencies

```bash
uv add google-genai duckdb pydantic python-dotenv
```

---

## 4. Configure Environment Variables

Create:

```text
.env
```

Add:

```bash
GEMINI_API_KEY=your_api_key_here
```

Do **not** commit this file.

A safe repository template can contain:

```text
.env.example
```

with:

```bash
GEMINI_API_KEY=your_api_key_here
```

---

# Running the Application

Launch the interactive CLI:

```bash
uv run python cli.py
```

You can then ask business questions through the terminal.

Example:

```text
What was the total revenue by region?
```

The agent will determine which tables and schemas it needs, execute SQL through its tools, and synthesize an answer from the database result.

---

# Evaluation

The evaluation layer tests whether the agent behaves correctly across a predefined benchmark suite.

The architecture is:

```text
test_suite.json
       ↓
    runner.py
       ↓
    run_agent()
       ↓
 Agent Response
       ↓
 ┌───────────────┐
 │ L1 Evaluator  │
 └───────────────┘
       +
 ┌───────────────┐
 │ L2 LLM Judge  │
 └───────────────┘
```

This provides more confidence than manually testing a few prompts.

---

# Observability

Agent events are recorded as append-only JSONL telemetry:

```text
traces/log_records.jsonl
```

The telemetry can then be ingested into DuckDB for analytical queries.

This separates:

```text
Operational execution
        ↓
Raw telemetry
        ↓
Analytical storage
        ↓
Metrics and debugging
```

---

# Engineering Problems Solved

Building the system exposed several realistic AI engineering problems.

## Gemini Quota Exhaustion

### Symptom

```text
429 RESOURCE_EXHAUSTED
```

### Cause

Evaluation requests were sent faster than the available API quota allowed.

### Solution

Retry and exponential-backoff behavior was introduced.

### Lesson

AI applications depend on external infrastructure and therefore need explicit rate-limit handling.

---

## Complex Join Exceeded Agent Step Budget

A three-table evaluation required more reasoning/tool interactions than the original step budget permitted.

The original limit was insufficient.

The agent's maximum step count was increased to:

```python
MAX_STEPS = 8
```

### Lesson

Agent iteration limits must balance two competing requirements:

```text
Too Low
   ↓
Legitimate tasks fail

Too High
   ↓
Runaway loops + higher cost
```

---

## Incorrect Token Accounting

Token usage was accidentally accumulated incorrectly across agent turns.

This caused the application to believe the token budget had been exhausted earlier than it actually had.

The tracking logic was corrected so the reported usage was interpreted appropriately against the context ceiling.

### Lesson

Never assume an API usage field represents incremental usage.

Understand whether metrics are:

```text
per request
per turn
or
cumulative
```

before aggregating them.

---

## DuckDB Session Status Bug

Telemetry initially reported successful sessions as failures.

The problematic pattern involved:

```sql
MAX(
    CASE
        WHEN type = 'session_end'
        THEN data->>'reason'
        ELSE 'incomplete'
    END
)
```

`MAX()` was operating lexicographically on strings.

The corrected pattern eliminated the misleading fallback value from the aggregation:

```sql
COALESCE(
    MAX(
        CASE
            WHEN type = 'session_end'
            THEN data->>'reason'
        END
    ),
    'incomplete'
)
```

### Lesson

SQL aggregation functions operate according to data types.

`MAX()` over text means lexical ordering—not semantic importance.

---

# Safety

The project uses multiple layers of defensive engineering.

### Database Safety

Database access is restricted to read-oriented SQL rather than unrestricted mutation.

### Agent Safety

Execution is bounded by:

```text
Maximum Steps
Maximum Runtime
Maximum Token Budget
```

### Secret Safety

API credentials belong in:

```text
.env
```

and should be excluded through:

```text
.gitignore
```

### Grounding

Business values should originate from deterministic database results rather than LLM memory or arithmetic.

---

# Architectural Decisions

| Decision | Choice | Reason |
|---|---|---|
| Analytical Database | DuckDB | Local, embedded and optimized for analytical workloads |
| AI Architecture | ReAct-style agent | Allows iterative schema discovery and tool execution |
| Data Access | Deterministic tools | Creates a controlled boundary between AI and data |
| Telemetry | JSONL | Simple append-oriented structured logging |
| Evaluation | L1 + L2 | Combines deterministic verification with semantic grading |
| Dependency Management | `uv` | Reproducible modern Python workflow |
| Initial Interface | CLI | Simple environment for end-to-end testing |

---

# What This Project Demonstrates

This project demonstrates practical knowledge across several engineering disciplines.

### Agentic AI

- agent loops,
- tool calling,
- schema discovery,
- ReAct architecture,
- execution limits,
- model fallback.

### Data Engineering

- structured telemetry,
- JSONL,
- ingestion,
- analytical querying,
- DuckDB.

### LLMOps

- tracing,
- evaluation,
- token monitoring,
- latency monitoring,
- failure analysis.

### Software Engineering

- modular architecture,
- environment management,
- secret management,
- debugging,
- defensive execution,
- separation of concerns.

---

# Key Engineering Lesson

The central lesson of the project is that building an AI agent is not simply:

```text
Prompt → LLM → Answer
```

A more reliable system requires:

```text
                  ┌───────────────┐
                  │      LLM      │
                  │   Reasoning   │
                  └───────┬───────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ Controlled    │
                  │    Tools      │
                  └───────┬───────┘
                          │
                          ▼
                  ┌───────────────┐
                  │ Deterministic │
                  │     Data      │
                  └───────────────┘

                         +

                  Evaluation
                  Observability
                  Safety
                  Testing
```

The LLM is one component of the system—not the entire system.

---

# Roadmap

## Completed

- [x] Stage 0 — Project setup
- [x] Stage 1 — Database tooling
- [x] Stage 2 — ReAct agent
- [x] Stage 3 — Evaluation framework
- [x] Stage 4 — Observability pipeline
- [x] Stage 5 — Interactive CLI

## Planned

### Stage 6 — FastAPI REST API

The next planned stage is to expose the agent through an HTTP interface.

Conceptually:

```text
Client
   ↓
POST /chat
   ↓
FastAPI
   ↓
Agent
   ↓
Tools
   ↓
DuckDB
   ↓
Response
```

Important future concerns include:

- asynchronous execution,
- concurrent requests,
- request validation,
- API error handling,
- production deployment,
- authentication,
- rate limiting.

> **Stage 6 is planned future work and is not presented as part of the currently completed implementation.**

---

# Portfolio Summary

> Built an autonomous sales database agent using Python, Gemini and DuckDB. The system uses a ReAct-style agent loop to dynamically inspect database schemas, execute controlled read-only SQL, and generate grounded answers from real query results. I also developed a dual-layer evaluation framework and an observability pipeline using structured JSONL telemetry and DuckDB analytics, with safety controls for iteration limits, execution time, token usage and API failures.

---

# Current Status

```text
Stage 0  ██████████  COMPLETE
Stage 1  ██████████  COMPLETE
Stage 2  ██████████  COMPLETE
Stage 3  ██████████  COMPLETE
Stage 4  ██████████  COMPLETE
Stage 5  ██████████  COMPLETE
Stage 6  ░░░░░░░░░░  PLANNED
```

The project currently provides a complete local Agentic AI workflow from natural-language question → autonomous database exploration → deterministic SQL execution → grounded response → evaluation → telemetry.

The next architectural milestone is exposing this system through a **FastAPI REST interface**.
