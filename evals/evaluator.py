"""Evaluation engine: Deterministic heuristics (L1) and semantic LLM-as-a-Judge (L2)."""

import json
import re
from typing import Any, Dict

from google import genai
from google.genai import types
from sales_agent.config import configured_model
from sales_agent.models import ModelError, discover_model, generate, get_client
import time

JUDGE_PROMPT_TEMPLATE = """
You are an impartial evaluator grading an AI Sales Database Analyst.
Evaluate the model's final response against the user question and the ground truth.

Evaluation Criteria:
1. If Ground Truth is 'REFUSAL':
   - The question is out-of-scope (e.g., general coding, trivia, scraping).
   - Did the model politely refuse and steer the user back to sales analytics?
   - Award 5/5 if it refused cleanly without answering the off-topic request.
   - Award 1/5 if it attempted to answer the off-topic prompt.

2. If Ground Truth contains factual data (Numeric / Entity / Empty Set):
   - Correctness: Does the response state the accurate numerical or entity answer?
   - Empty Set Handling: If no records match, did it accurately state that zero records exist?
   - Grounding: Did the model explain the result consistent with the database findings?
   - Award 5/5 for accurate, well-grounded answers.
   - Deduct points for mathematical discrepancies, hallucinations, or ungrounded claims.

User Question: {question}
Ground Truth: {ground_truth}
Agent Response: {response}

Output your evaluation strictly in JSON format matching this schema:
{{
  "score": <integer from 1 to 5>,
  "reason": "<concise 1-sentence justification>"
}}
"""


class Evaluator:
    """Evaluates agent responses using zero-cost deterministic heuristics and resilient LLM judging."""

    def __init__(
        self,
        client: genai.Client | None = None,
        judge_model: str | None = None,
    ):
        self.client = client
        self.judge_model = judge_model

    def evaluate_deterministic(self, test_case: Dict[str, Any], agent_response: str) -> Dict[str, Any]:
        """Apply zero-cost L1 deterministic grading rules."""
        passed = True
        reasons = []

        # 1. Refusal Tier Check
        if test_case.get("should_refuse"):
            refusal_signals = [
                "cannot",
                "unable",
                "only answer",
                "sales data",
                "off-topic",
                "sorry",
                "focused on the sales database",
            ]
            refused = any(sig in agent_response.lower() for sig in refusal_signals)
            if not refused:
                passed = False
                reasons.append("Failed to refuse an out-of-scope query.")
            return {"l1_passed": passed, "reasons": reasons}

        # 2. Numeric / Empty Set Extraction
        expected_num = test_case.get("expected_numeric_answer")
        if expected_num is not None:
            clean_text = agent_response.replace(",", "")
            matches = [float(x) for x in re.findall(r"[-+]?\d*\.\d+|\d+", clean_text)]
            num_matched = any(abs(m - float(expected_num)) < 0.01 for m in matches)

            # Support natural language expressions for empty sets / zero quantities
            if not num_matched and float(expected_num) == 0.0:
                zero_phrases = [
                    "no revenue",
                    "no orders",
                    "no records",
                    "zero",
                    "none found",
                    "no customers",
                    "$0",
                ]
                if any(phrase in agent_response.lower() for phrase in zero_phrases):
                    num_matched = True

            if not num_matched:
                passed = False
                reasons.append(f"Expected number {expected_num} not found in response.")

        # 3. Entity Substring Check
        expected_entity = test_case.get("expected_entity_answer")
        if expected_entity and expected_entity.lower() not in agent_response.lower():
            passed = False
            reasons.append(f"Expected entity '{expected_entity}' missing from response.")

        return {"l1_passed": passed, "reasons": reasons}

    def evaluate_judge(self, test_case: Dict[str, Any], agent_response: str) -> Dict[str, Any]:
        """Apply L2 semantic grading via LLM-as-a-Judge with bounded provider retry and typed unavailability."""
        if test_case.get("should_refuse"):
            ground_truth = "REFUSAL (Expected clear, polite refusal of out-of-scope request)"
        else:
            parts = []
            if test_case.get("expected_numeric_answer") is not None:
                parts.append(f"Numeric: {test_case['expected_numeric_answer']}")
            if test_case.get("expected_entity_answer"):
                parts.append(f"Entity: {test_case['expected_entity_answer']}")
            ground_truth = ", ".join(parts) if parts else "Factual query result"

        prompt = JUDGE_PROMPT_TEMPLATE.format(
            question=test_case["question"],
            ground_truth=ground_truth,
            response=agent_response,
        )

        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        )

        try:
            if self.client is None:
                self.client = get_client()
            if self.judge_model is None:
                self.judge_model = discover_model(self.client, preferred=configured_model())
            resp = generate(
                self.client, model=self.judge_model, contents=prompt, config=config, deadline=time.monotonic() + 45
            )
            data = json.loads(resp.text or "{}")
            score = data.get("score")
            if type(score) is not int or not 1 <= score <= 5:
                raise ValueError("Invalid score")
            return {"judge_score": score, "judge_reason": "Model judge completed.", "judge_status": "SUCCESS"}
        except ModelError as exc:
            return {"judge_score": None, "judge_reason": "Judge unavailable.", "judge_status": str(exc.category)}
        except ValueError, TypeError, AttributeError:
            return {
                "judge_score": None,
                "judge_reason": "Invalid judge response.",
                "judge_status": "MALFORMED_RESPONSE",
            }
