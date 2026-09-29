# Sales-DB Autonomous Agent

An autonomous sales analytics agent that translates natural-language business questions into safe, verified SQL queries over a PostgreSQL sales database using semantic schema discovery, defense-in-depth query guardrails, and dynamic LLM model selection.

---

## Technical Stack & Architecture

- **Runtime & Environment:** Python 3.12+, managed via `uv`.
- **LLM & Function Calling:** Google Gemini API (`google-genai` SDK) with dynamic runtime endpoint discovery.
- **Relational Data Store:** PostgreSQL 16 enforcing relational integrity (`sales.customers`, `sales.products`, `sales.orders`).
- **Semantic Layer & Vector Store:** `pgvector` with HNSW indexing (`vector_cosine_ops`) over business schema documentation cards.
- **Embedding Engine:** Local, CPU-optimized ONNX runtime inference (`Xenova/all-MiniLM-L6-v2`) generating normalized 384-dimensional dense vectors without heavy framework overhead.
- **Security & Guardrails:** Strict read-only query tripwires, AST-level mutation blocking (`INSERT`, `UPDATE`, `DROP`, etc.), automatic subquery wrapping, and result set row capping (`LIMIT 20`).

---

## Implementation Roadmap

- [x] **Stage 0: Environment & Database Foundations**
  - Dependency isolation and lockfile management via `uv`.
  - PostgreSQL 16 database provisioning with relational schemas, foreign keys, and seed data.
  - Secret isolation using `.env` boundaries.

- [x] **Stage 1: Semantic Schema Retrieval Layer**
  - Local ONNX embedding engine (`OnnxEmbedder`) producing L2-normalized 384-d vectors.
  - In-database vector store (`schema_docs`) using `pgvector` with HNSW cosine indexing.
  - Semantic router ingestion and top-$k$ retrieval verification against business queries.

- [x] **Stage 2: Tool Contracts & Execution Guardrails**
  - Schema discovery actuators: `list_tables` and `describe_table` via `information_schema`.
  - Semantic tool integration: `search_schema` backed by `pgvector`.
  - Safe query executor: `run_sql` with regex tripwires, semicolon sanitization, and subquery row limits.
  - Dynamic Gemini model discovery prioritizing low-latency tool-calling endpoints (`gemini-2.5-flash`).

- [ ] **Stage 3: Autonomous Agentic Loop (ReAct)**
  - Dynamic reasoning, execution, error observation, and self-correction cycles.
  - Token and step budget caps.

- [ ] **Stage 4: Model Context Protocol (MCP)**
  - Out-of-process capability serving over `stdio` via FastMCP.

- [ ] **Stage 5: Observability & Analytical Store**
  - Pipeline trace ingestion via `dlt` into DuckDB; interactive dashboards with Marimo.

- [ ] **Stage 6: System Evaluations & Benchmarking**
  - Retrieval metrics (MRR, Hit Rate@K) and trajectory execution grading.

---

## Security & Guardrails

- **Zero Mutation Surface:** The database interface permits only read-only `SELECT` and `WITH` statements. Modifying statements (`DROP`, `ALTER`, `TRUNCATE`, `DELETE`, `UPDATE`) are rejected before touching the connection.
- **Unbounded Scan Protection:** All incoming queries are sanitized and wrapped in an outer subquery (`LIMIT 21`) to prevent token exhaustion and out-of-memory errors.
- **Zero Secret Exposure:** Credentials and API keys reside exclusively in local environment files ignored by version control.

---

## License & Intellectual Property

Copyright 2026 Akshay Runthala. All rights reserved.

This source code and related documentation are made publicly available on GitHub strictly for viewing, inspection, and reference purposes. No license is granted to copy, reproduce, modify, distribute, publish, sublicense, or create derivative works from any part of this software without prior express written permission. Refer to `LICENSE` for formal terms.
