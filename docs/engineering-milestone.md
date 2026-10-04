# Current architecture audit and engineering milestone

Source re-inspected on 2026-10-04. No production DB, secret configuration,
historical traces, live Gemini, or mutating verification was accessed. Existing
README local edits are preserved verbatim in a marked historical section.

## Before changes: contracts and wiring

| File / function | Input -> output | Caller | Side effects | Failure mode |
|---|---|---|---|---|
| root cli.py / main | Question -> printed run_agent text | Manual terminal | stdin/stdout; runtime calls | Raw exception output |
| agent.py / run_agent | Question, model -> text | root CLI, benchmark | Eager client; model calls; trace writes | Duplicates execute, blank final, unverified prose |
| tools.py / five functions | Tool args -> dictionaries/lists | Agent, verification, existing MCP | PostgreSQL reads; optional embedding | Regex-only SQL, raw error strings |
| db.py / get_conn | DATABASE_URL -> connection | Tools, expansion seed | dotenv at import; connections | No explicit read-only/timeout |
| schema_store.py / init_store, load_docs, search_docs | Cards/query -> rows/hits | search_schema, stage1 | Eager embedder, DB writes/reads | Unqualified table conflicts with seed layout |
| embedder.py / OnnxEmbedder.encode | Text -> 384-number vector | Store | Local assets / ONNX execution | Missing model; unmasked pooling |
| trace.py / TraceLogger | Question/tool args/text -> events | Agent | JSONL with private payloads | Exceptions leave no end; no outcome rows |
| ingest.py / ingest | JSONL -> DuckDB | Explicit loader | Pipeline constructed at import; append writes | Repeated loads duplicate events |
| evaluator.py / Evaluator | Expected cases + text -> L1/L2 | eval runner | Eager client, live judge | API failure scored as 1; weak L1 occurrence tests |
| models.py / discover_model | Client -> catalog choice | verify_stage2 | dotenv; inventory network | Not connected to active loop |
| gateway.py / resolve_provider_and_model | Config names -> provider/model | No active loop caller | Env reads only on invocation | Unused naming helper, not live routing |
| package cli.py / main | Question -> SalesAgent.run | console sales-agent | Intended live calls | Missing SalesAgent import |
| app.py | UI prompt -> SalesAgent.run | Streamlit | Display history | Missing class; misleading providers/AST caption |
| sales_db_agent.main | No input -> greeting | console sales-db-agent | stdout | Does not start agent |
| mcp_server.py | Two requests -> existing tools | Optional manual process | Existing FastMCP transport | Not the root CLI path |
| dashboard/traces_app.py | Session filter -> analytics | Marimo | Read-only DuckDB | Interpolated filter; raw data-column assumption |
| scripts/verify_stage1 + test_stage1 | Known queries -> assertions | Manual integration | Writes PG; local model | Not offline; incorrect universal 0..1 score assumption |
| scripts/verify_stage2 | Tools/catalog -> assertions | Manual integration | PG + model inventory | Not offline |
| scripts/verify_stage3 | Question -> comparison | Manual end-to-end | PG + Gemini + traces | Missing class |
| scripts/verify_stage5 | Trace DB -> metrics | Manual history check | Reads local DB | Peak event mislabeled session usage |
| seed scripts / data/seed.sql | Fixture rows -> PG | Manual maintenance | Business data writes | Different fixtures; legacy metadata layout |

The active question path was root CLI -> run_agent -> Gemini -> manual tools ->
PostgreSQL -> tool observations -> arbitrary model prose. RAG was 12 guidance
cards -> local embedding -> unqualified schema_docs -> search_schema -> model.
History was TraceLogger -> JSONL -> dlt -> DuckDB, separate from sales facts.

## Verified priorities

P0: broken class/entry-point integration; duplicate execution; unsupported data
answers; SQL text checks without a DB read-only boundary; incompatible retrieval
identities; sensitive payload logging/raw error exposure.

P1: eager imports/clients/embedder/pipeline; untyped API fallback including quota,
auth and configuration failures; missing guaranteed trace closure; no offline
runner; judge availability conflated with quality; dashboard filter interpolation.

P2: stale README and fixture assumptions; unused multi-provider helper; coarse
L1 checks; append-only history ingestion duplicates; peak usage naming.

P3 (not added): new providers, agents, web/PDF RAG, servers, deployments or rerankers.

## Decision record / authoritative references

- Manual application dispatch preserves original model content and function-call
  IDs, as described by [Google function calling](https://ai.google.dev/gemini-api/docs/function-calling).
- [Psycopg transactions](https://www.psycopg.org/psycopg3/docs/basic/transactions.html)
  allow read_only characteristics before a transaction starts. We set those on
  runtime connections, with separately authorized setup writes.
- [PostgreSQL timeouts and search_path](https://www.postgresql.org/docs/current/runtime-config-client.html)
  motivate per-connection statement/lock limits and explicit table identities.
  Read-only transactions do not replace least privilege or prohibit all side effects.
- [SQLGlot](https://github.com/tobymao/sqlglot) parses scoped query structure;
  it was already installed/locked transitively and is now a declared direct
  dependency at the existing resolved major version. No new parser framework.
- [pgvector](https://github.com/pgvector/pgvector) supplies vector(384), cosine
  operators and the existing HNSW index. Similarity remains guidance, not truth.
- [Gemini troubleshooting](https://ai.google.dev/gemini-api/docs/troubleshooting)
  distinguishes 400/401/403/404/429/provider errors. Same-model retry is bounded
  for transient provider failures; terminal failures do not rotate models.

## Safe retrieval transition (manual; not executed)

1. Review existing relations using an authorized maintenance account separately.
2. Keep public.schema_docs and sales.schema_docs intact; do not rename or drop.
3. Run the shared init_store setup to create sales.schema_cards with text IDs,
   kind/name/table_name/description and non-null vector(384), plus its HNSW index.
4. Rebuild cards from the public JSONL with load_docs. This is an explicit write
   operation; use the same local model for card loading and query embeddings.
5. Verify expected cards using isolated integration fixtures before a live run.
6. Retire legacy tables only through a future explicit owner-approved operation.

No implicit old-data copy or search_path-dependent migration is performed.
ID upserts are idempotent; removal of obsolete IDs is a separate maintenance
decision. No threshold or reranker was introduced without measured evidence.

## After changes

One SalesAgent loop backs run_agent, root/package CLI, both console commands,
UI and benchmarks. Injection is plain Python. SQLGlot policy -> read-only PG ->
bounded SQL observation -> evidence-reference validation -> deterministic facts.
Schema/help/refusal use separate contracts. No arbitrary model prose is rendered
as a business-data answer. Query intent remains an explicit limitation.

Traces are versioned safe metadata; end events are attempted in finally. Loader
construction is lazy; analytics remains separate and append-based. No historical
payloads are opened or rewritten. UI/history scripts remain optional integrations.

## Self-review and testing

Tests caught the initially missing sampling-query exclusion. Review found model
override validation, configurable request timeout, malformed argument types,
NULL/no-data semantics and trace-write failure visibility needed strengthening.
Those were corrected before rerunning the offline suite. Matching-number prose
is deliberately rejected; reference validation is not represented as semantic
SQL correctness. All application integrations remain unexecuted in this milestone.

The approved runner blocks network/DNS, real model and DB clients, dotenv,
secret files, production databases/history and model assets before collection.
Tests use fakes and temp files. Exact final counts/commands are reported in the
delivery message. User review and manual commit/push remain separate steps.

Self-review additionally tightened nested DML/DDL and constant-only query exclusions, public extension placement, public-card metadata allowlisting, late-response timeout checks, lazy maintenance imports and judge score bounds. No real retrieval-quality score is claimed: five expected-card cases are defined for a future isolated integration run.
