"""Autonomous agentic loop: multi-turn reasoning with safety tripwires, fallback, and telemetry."""
import json
import time
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai.errors import APIError

from sales_agent.tools import describe_table, list_tables, run_sql, search_schema
from sales_agent.trace import TraceLogger

load_dotenv()
client = genai.Client()

# Safety Tripwires per Stage 3 specification
MAX_STEPS = 6        # Tripwire 1: Iteration cap
MAX_SECONDS = 45     # Tripwire 2: Wall-clock timeout
MAX_TOKENS = 15_000  # Tripwire 3: Cumulative token budget

# Resilient Model Fallback Chain
MODEL_CHAIN = [
    "gemini-flash-lite-latest",
    "gemini-3-flash-preview",
]

INSTRUCTIONS = """
You are a sales data analyst. Answer business questions using the sales DB.

WORKFLOW LAWS:
1. Start with search_schema to find relevant tables/columns; use describe_table
   for exact column names before writing SQL.
2. DO NOT stop after the first lookup. If results miss facts (region, date
   range, status), search again with refined keywords.
3. Write a read-only SELECT. If run_sql returns an error, read it, fix the SQL,
   and retry.
4. Answer ONLY from returned rows - never invent numbers. If the query returns
   nothing relevant, say what you could not find.
5. Show the SQL you used, then a short answer with the numbers.

SCOPE & RELEVANCE RULES:
1. ONLY answer questions about sales data: revenue, orders, customers,
   products, regions, trends.
2. For off-topic questions (trivia, politics, coding help), DO NOT use general
   knowledge. Refuse politely and guide the user back to sales analytics.
"""

TOOL_FUNCS = {
    "list_tables": list_tables,
    "describe_table": describe_table,
    "search_schema": search_schema,
    "run_sql": run_sql,
}


def _generate_with_fallback(contents, config, preferred_model: str):
    """Attempt generation with primary model; fail over on 429/503 errors."""
    models_to_try = [preferred_model] + [m for m in MODEL_CHAIN if m != preferred_model]
    last_error = None

    for m in models_to_try:
        try:
            return client.models.generate_content(
                model=m, contents=contents, config=config
            )
        except APIError as exc:
            last_error = exc
            err_msg = str(exc)
            # Catch transient capacity (503) or rate limits (429)
            if "503" in err_msg or "429" in err_msg:
                time.sleep(1.0)
                continue
            raise exc

    raise last_error


def run_agent(question: str, model: str = "gemini-flash-lite-latest") -> str:
    """Execute the multi-turn ReAct reasoning loop over sales data with full telemetry."""
    t0 = time.time()
    tokens = 0
    seen_calls: set = set()  # Tripwire 4: duplicate call guard
    trace = TraceLogger(question)

    contents = [types.Content(role="user", parts=[types.Part(text=question)])]
    config = types.GenerateContentConfig(
        system_instruction=INSTRUCTIONS,
        tools=[list_tables, describe_table, search_schema, run_sql],
        automatic_function_calling=types.AutomaticFunctionCallingConfig(disable=True),
    )

    for step in range(1, MAX_STEPS + 1):
        if time.time() - t0 > MAX_SECONDS:
            trace.close("timeout")
            return "Query timed out - try narrowing the question."

        response = _generate_with_fallback(contents, config, preferred_model=model)

        tokens += (response.usage_metadata.total_token_count if response.usage_metadata else 0) or 0
        trace.usage(tokens)

        if tokens > MAX_TOKENS:
            trace.close("budget")
            return "Answer budget exceeded - try a simpler question."

        tool_calls = response.function_calls or []
        if not tool_calls:
            text = response.text or ""
            trace.assistant(text)
            trace.close("done")
            return text

        contents.append(response.candidates[0].content)

        for fn in tool_calls:
            args = dict(fn.args or {})
            key = (fn.name, json.dumps(args, sort_keys=True))

            if key in seen_calls:
                payload = {"error": "Duplicate call blocked."}
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

    trace.close("max_steps")
    return "I couldn't complete this analysis - please refine the question."
