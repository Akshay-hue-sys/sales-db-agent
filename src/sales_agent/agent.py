"""Autonomous agentic loop: multi-turn reasoning with safety tripwires, fallback, and telemetry."""

import json
import logging
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

from sales_agent.tools import (
    describe_table,
    get_schema,
    list_tables,
    run_sql,
    search_schema,
)
from sales_agent.trace import TraceLogger

# Suppress SDK informational diagnostic regarding manual function calling in generate_content
logging.getLogger("google.genai").setLevel(logging.ERROR)
logging.getLogger("google.genai.models").setLevel(logging.ERROR)
logging.getLogger("google.genai._api_client").setLevel(logging.ERROR)

load_dotenv()
client = genai.Client()

# Safety Tripwires
MAX_STEPS = 8        # Tripwire 1: Hard iteration cap (accommodates 3-way join discovery)
MAX_SECONDS = 45     # Tripwire 2: Wall-clock timeout
MAX_TOKENS = 30_000  # Tripwire 3: Context window ceiling (linear turn check)

# Resilient Model Fallback Chain
MODEL_CHAIN = [
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
]

INSTRUCTIONS = """
You are an expert sales data analyst. Answer business questions using the sales database.

WORKFLOW LAWS:
1. Start with get_schema() to discover available tables. When exploring a specific table,
   call get_schema(table_name="sales.tablename") to retrieve exact column names, data types,
   and foreign-key join paths before writing any SQL.
2. If get_schema provides what you need, proceed directly to run_sql. Use search_schema only
   if you need high-level business definitions or domain guidance.
3. Write a read-only SELECT. If run_sql returns an error, read it carefully, fix the SQL syntax,
   and retry.
4. Answer ONLY from returned database rows - never invent numbers or extrapolate unreturned data.
   If the query returns zero rows, state clearly what could not be found.
5. Show the SQL you used, followed by a concise summary answering the user's question with the exact data.

SCOPE & RELEVANCE RULES:
1. ONLY answer questions about sales analytics: revenue, orders, customers, products, regions, and trends.
2. For off-topic questions (e.g., general coding, trivia, politics, creative writing), refuse politely
   and guide the user back to the sales database.
"""

# Deterministic Tool Dispatch Table
TOOL_FUNCS = {
    "get_schema": get_schema,
    "list_tables": list_tables,
    "describe_table": describe_table,
    "search_schema": search_schema,
    "run_sql": run_sql,
}


def _generate_with_fallback(contents, config, preferred_model: str):
    """Attempt generation with primary model; retry with exponential backoff on 429/503 before failing over."""
    models_to_try = [preferred_model] + [m for m in MODEL_CHAIN if m != preferred_model]
    last_error = None
    max_attempts_per_model = 3

    for model_name in models_to_try:
        for attempt in range(max_attempts_per_model):
            try:
                return client.models.generate_content(
                    model=model_name, contents=contents, config=config
                )
            except APIError as exc:
                last_error = exc
                err_msg = str(exc)
                is_transient = any(
                    code in err_msg
                    for code in ["503", "429", "UNAVAILABLE", "RESOURCE_EXHAUSTED"]
                )

                if is_transient and attempt < max_attempts_per_model - 1:
                    sleep_time = 2.0 * (2 ** attempt)  # 2s, 4s backoff
                    time.sleep(sleep_time)
                    continue

                # If non-transient or retries exhausted for this model, fall through to next model
                break

    raise last_error


def run_agent(question: str, model: str = "gemini-flash-lite-latest") -> str:
    """Execute the multi-turn ReAct reasoning loop over sales data with full telemetry."""
    t0 = time.time()
    seen_calls: set = set()  # Tripwire 4: duplicate call cycle guard
    trace = TraceLogger(question)

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCTIONS,
        tools=[get_schema, list_tables, describe_table, search_schema, run_sql],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for step in range(1, MAX_STEPS + 1):
        # Tripwire 2: Wall-clock timeout check
        if time.time() - t0 > MAX_SECONDS:
            trace.close("timeout")
            return "Query timed out - try narrowing the question."

        response = _generate_with_fallback(contents, config, preferred_model=model)

        turn_tokens = (
            response.usage_metadata.total_token_count
            if response.usage_metadata
            else 0
        ) or 0
        trace.usage(turn_tokens)

        # Tripwire 3: Context window ceiling check
        if turn_tokens > MAX_TOKENS:
            trace.close("budget")
            return "Answer budget exceeded - try a simpler question."

        tool_calls = response.function_calls or []

        # Natural loop termination: Model generated a final textual response
        if not tool_calls:
            text = response.text or ""
            trace.assistant(text)
            trace.close("done")
            return text

        # Record assistant tool call intent into conversation context
        contents.append(response.candidates[0].content)

        # Process each tool call requested by the model
        for fn in tool_calls:
            args = dict(fn.args or {})
            key = (fn.name, json.dumps(args, sort_keys=True))

            # Tripwire 4: Block duplicate calls with identical arguments
            if key in seen_calls:
                payload = {
                    "error": "Duplicate call blocked: You already executed this exact call."
                }
            else:
                seen_calls.add(key)
                trace.tool_call(fn.name, args)

            func = TOOL_FUNCS.get(fn.name)
            if func is None:
                payload = {"error": f"Unknown tool '{fn.name}'."}
            else:
                try:
                    result = func(**args)
                except Exception as exc:
                    result = {"error": str(exc)}
                payload = result if isinstance(result, dict) else {"result": result}

            # Return tool observation back to the model as a FunctionResponse part
            contents.append(
                types.Content(
                    role="user",
                    parts=[
                        types.Part(
                            function_response=types.FunctionResponse(
                                name=fn.name, response=payload
                            )
                        )
                    ],
                )
            )

    # Tripwire 1: Reached max iteration ceiling without synthesis
    trace.close("max_steps")
    return "I couldn't complete this analysis within the step limit - please refine the question."