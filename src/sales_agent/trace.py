"""Versioned metadata-only JSONL telemetry. Never store inputs or results."""

import json
import math
import time
import uuid
from pathlib import Path

TRACE_DIR = Path(__file__).resolve().parents[2] / "traces"


class TraceLogger:
    def __init__(self, question, directory=None, clock=time.monotonic):
        self.directory = Path(directory) if directory is not None else TRACE_DIR
        self.clock = clock
        self.started = clock()
        self.session_id = str(uuid.uuid4())
        self.closed = False
        self.failed = False
        self.public_card_ids = None
        self._log("user", {"question_chars": len(question)})

    def _log(self, kind, data):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            rec = {
                "trace_version": 2,
                "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
                "session_id": self.session_id,
                "agent": "sales-analyst",
                "type": kind,
                "data": data,
            }
            with (self.directory / "log_records.jsonl").open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
        except OSError:
            self.failed = True  # Observability failure must not expose exception details.

    def tool_call(self, name, args):
        self._log(
            "tool_use",
            {
                "name": name
                if name in {"get_schema", "list_tables", "describe_table", "search_schema", "run_sql"}
                else "unknown"
            },
        )

    def tool_outcome(self, name, status, seconds, result):
        data = {
            "name": name
            if name in {"get_schema", "list_tables", "describe_table", "search_schema", "run_sql"}
            else "unknown",
            "status": str(status),
            "duration_seconds": round(seconds, 4),
        }
        if isinstance(result, dict) and "rows" in result:
            data.update(row_count=len(result["rows"]), truncated=bool(result.get("truncated")))
        if name == "search_schema" and isinstance(result, list):
            # Only IDs present in the public configured file may enter telemetry.
            if self.public_card_ids is None:
                try:
                    from sales_agent.schema_store import read_cards

                    self.public_card_ids = {r["id"] for r in read_cards()}
                except OSError, ValueError, TypeError:
                    self.public_card_ids = set()
            data["card_ids"] = [r["id"] for r in result if isinstance(r, dict) and r.get("id") in self.public_card_ids]
            data["scores"] = [
                r["similarity"]
                for r in result
                if isinstance(r, dict) and type(r.get("similarity")) in (int, float) and math.isfinite(r["similarity"])
            ]
        self._log("tool_outcome", data)

    def usage(self, tokens):
        self._log("usage", {"total_tokens": tokens})

    def model_request(self, model, seconds, status):
        self._log("model_request", {"model": model, "status": str(status), "duration_seconds": round(seconds, 4)})

    def assistant(self, text):
        self._log("assistant", {"answer_chars": len(text)})

    def close(self, reason):
        if not self.closed:
            self.closed = True
            self._log("session_end", {"reason": str(reason), "duration_seconds": round(self.clock() - self.started, 4)})
