"""Non-secret settings. Configuration is resolved only when used."""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class AgentConfig:
    max_steps: int = 8
    max_seconds: float = 45
    max_tokens: int = 30_000
    max_tool_calls_per_turn: int = 5
    request_timeout_seconds: float = 15
    model: str | None = None

    def __post_init__(self):
        if any(type(v) is not int for v in (self.max_steps, self.max_tokens, self.max_tool_calls_per_turn)):
            raise ValueError("Step and request budgets must be integers.")
        if self.model is not None and (
            not isinstance(self.model, str) or not self.model.strip() or len(self.model) > 100
        ):
            raise ValueError("Invalid configured model identifier.")
        if not 1 <= self.max_steps <= 32 or not 1 <= self.max_seconds <= 300:
            raise ValueError("Invalid step/time bounds.")
        if not 1 <= self.max_tokens <= 100_000 or not 1 <= self.max_tool_calls_per_turn <= 10:
            raise ValueError("Invalid budget bounds.")
        if not 1 <= self.request_timeout_seconds <= 60:
            raise ValueError("Invalid request timeout.")


def configured_model():
    return os.environ.get("GEMINI_MODEL") or None
