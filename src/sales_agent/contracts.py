"""Python-owned evidence and deliberately narrow final-answer rendering."""

import json
from dataclasses import dataclass
from enum import StrEnum


class Status(StrEnum):
    SUCCESS = "SUCCESS"
    NO_DATA = "NO_DATA"
    INVALID_REQUEST = "INVALID_REQUEST"
    DATABASE_ERROR = "DATABASE_ERROR"
    RETRIEVAL_ERROR = "RETRIEVAL_ERROR"
    MODEL_ERROR = "MODEL_ERROR"
    TOOL_ERROR = "TOOL_ERROR"
    POLICY_REJECTION = "POLICY_REJECTION"
    TIMEOUT = "TIMEOUT"


def error_result(status, code, message):
    return {"status": str(status), "error_code": code, "error": message}


@dataclass(frozen=True)
class SQLObservation:
    evidence_id: str
    sql: str
    columns: tuple[str, ...]
    rows: tuple[tuple[str | None, ...], ...]
    truncated: bool = False


@dataclass(frozen=True)
class AgentAnswer:
    answer_text: str
    status: Status = Status.SUCCESS
    sql_used: str | None = None
    supporting_rows: tuple = ()
    evidence_type: str = "none"
    warnings: tuple[str, ...] = ()


def render_database_answer(text, observations):
    """Validate cell references, then render facts rather than free-form prose.

    No model-written values, labels, currency, arithmetic or explanations enter
    data answers. This proves provenance, not correctness of the selected SQL.
    """
    try:
        data = json.loads(text)
        if not isinstance(data, dict) or set(data) != {"evidence_id", "row_indices"}:
            raise ValueError
        obs = observations[data["evidence_id"]]
        indices = data["row_indices"]
        if not isinstance(indices, list) or len(indices) > 20:
            raise ValueError
        if any(type(i) is not int or i < 0 or i >= len(obs.rows) for i in indices):
            raise ValueError
        if len(set(indices)) != len(indices) or (obs.rows and not indices):
            raise ValueError
        rows = tuple(obs.rows[i] for i in indices)
    except ValueError, TypeError, KeyError:
        return AgentAnswer("I cannot validate the final answer against database evidence.", Status.POLICY_REJECTION)
    lines = ["Database result:"]
    if not obs.rows:
        lines.append("No matching rows were returned.")
    for row in rows:
        lines.append(
            "; ".join(
                f"{col}: {val if val is not None else 'NULL (not a measured zero)'}"
                for col, val in zip(obs.columns, row, strict=True)
            )
        )
    warnings = ("Result truncated; this is not the complete result set.",) if obs.truncated else ()
    lines.extend(warnings)
    lines.extend(["SQL used:", obs.sql])
    return AgentAnswer(
        "\n".join(lines), Status.NO_DATA if not obs.rows else Status.SUCCESS, obs.sql, rows, "postgresql", warnings
    )
