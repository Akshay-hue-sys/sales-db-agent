"""JSONL trace logging: timestamp, session_id, agent, type, data."""
import json
import time
import uuid
from pathlib import Path

# Resolve traces directory relative to project root
TRACE_DIR = Path(__file__).resolve().parents[2] / "traces"


class TraceLogger:
    """Structured telemetry logger for agent reasoning steps and tool execution."""

    def __init__(self, question: str):
        TRACE_DIR.mkdir(exist_ok=True)
        self.session_id = str(uuid.uuid4())
        self._log("user", question)

    def _log(self, type_: str, data) -> None:
        rec = {
            "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "session_id": self.session_id,
            "agent": "sales-analyst",
            "type": type_,
            "data": data,
        }
        with open(TRACE_DIR / "log_records.jsonl", "a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")

    def tool_call(self, name: str, args: dict) -> None:
        """Log a tool invocation request."""
        self._log("tool_use", {"name": name, "args": args})

    def usage(self, tokens: int) -> None:
        """Log token consumption."""
        self._log("usage", {"total_tokens": tokens})

    def assistant(self, text: str) -> None:
        """Log the synthesized assistant response."""
        self._log("assistant", text)

    def close(self, reason: str) -> None:
        """Mark the session closed with a completion code."""
        self._log("session_end", {"reason": reason})
