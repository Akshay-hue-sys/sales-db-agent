"""Trace Pipeline: Ingest JSONL agent traces into DuckDB via dlt."""

import json
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
TRACE_FILE = PROJECT_ROOT / "traces" / "log_records.jsonl"
DUCKDB_PATH = PROJECT_ROOT / "sales-db-agent.duckdb"


def trace_records():
    """Generator reading raw JSONL execution trace lines."""
    if not TRACE_FILE.exists():
        print(f"[!] Warning: Trace file not found at {TRACE_FILE}")
        return

    with open(TRACE_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                yield json.loads(line)


def ingest() -> None:
    """Execute the ELT load job."""
    import dlt

    # Construct only for an explicitly invoked ingestion operation.
    pipeline = dlt.pipeline(
        pipeline_name="sales_agent_traces", destination=dlt.destinations.duckdb(str(DUCKDB_PATH)), dataset_name="traces"
    )
    info = pipeline.run(
        dlt.resource(trace_records(), name="log_records", primary_key="session_id", write_disposition="append")
    )
    print(info)


if __name__ == "__main__":
    ingest()
