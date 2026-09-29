"""Stage 3: Multi-Provider ReAct loop supporting Gemini, OpenAI, and Claude with explicit quota handling."""
import json
import re
import litellm
from litellm import completion

# Automatically strip unsupported or deprecated parameters across providers
litellm.drop_params = True
from litellm.exceptions import RateLimitError, AuthenticationError
litellm.drop_params = True

from sales_agent.gateway import resolve_provider_and_model
from sales_agent.tools import list_tables, describe_table, search_schema, run_sql

SYSTEM_INSTRUCTION = """You are an expert sales database analytics agent.
Your mission is to accurately answer natural-language business questions using a PostgreSQL database.

Follow this strict protocol:
1. DISCOVER: If you don't know the exact schema, call `search_schema(query=...)` or `list_tables()` first.
2. INSPECT: Call `describe_table(table_name=...)` if you need exact column names or data types.
3. EXECUTE: Construct a valid read-only PostgreSQL query and run it using `run_sql(sql=...)`.
   - Always filter or aggregate data appropriately.
   - If a query returns an error, carefully read the error message, correct your SQL, and retry.
4. SYNTHESIZE: Once you have the necessary data, provide a direct, concise, and helpful business answer.
   Always cite key numbers and metrics from your query results.
"""

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "list_tables",
            "description": "Lists all accessible tables and views in the database schema.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "describe_table",
            "description": "Returns column names, data types, and primary key metadata for a specified table.",
            "parameters": {
                "type": "object",
                "properties": {
                    "table_name": {"type": "string", "description": "The table name (e.g., 'sales.orders')"}
                },
                "required": ["table_name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search_schema",
            "description": "Performs semantic vector search against schema documentation to find relevant tables and business metrics.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "Natural language concept to search (e.g., 'revenue')"},
                    "limit": {"type": "integer", "description": "Maximum schema cards to return", "default": 3},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_sql",
            "description": "Safely executes a read-only SQL query against PostgreSQL with limit capping and AST mutation tripwires.",
            "parameters": {
                "type": "object",
                "properties": {
                    "sql": {"type": "string", "description": "Read-only ANSI/Postgres SQL query string"}
                },
                "required": ["sql"],
            },
        },
    },
]

TOOL_DISPATCHER = {
    "list_tables": list_tables,
    "describe_table": describe_table,
    "search_schema": search_schema,
    "run_sql": run_sql,
}

class SalesAgent:
    """Universal ReAct controller capable of executing across Gemini, OpenAI, or Anthropic."""

    def __init__(self, model_name: str | None = None, max_turns: int = 10):
        self.provider, self.model = resolve_provider_and_model(model_name)
        self.max_turns = max_turns
        litellm.suppress_debug_info = True

    def run(self, user_query: str) -> str:
        """Executes the multi-turn ReAct reasoning loop with explicit API failure boundaries."""
        messages = [
            {"role": "system", "content": SYSTEM_INSTRUCTION},
            {"role": "user", "content": user_query},
        ]

        for turn in range(self.max_turns):
            try:
                response = completion(
                    model=self.model,
                    messages=messages,
                    tools=TOOL_SCHEMAS,
                    tool_choice="auto",
                )
            except RateLimitError as err:
                error_str = str(err)
                retry_hint = ""
                match = re.search(r"retry in ([\d\.]+s?)", error_str)
                if match:
                    retry_hint = f" Please retry in {match.group(1)}."

                return (
                    f"Quota Exhausted: The API provider ({self.provider}) reported that the request quota "
                    f"for model '{self.model}' has been exceeded.{retry_hint} "
                    "To resolve this, wait for the quota window to reset, add credits to your provider account, "
                    "or configure an alternate API key (e.g., OPENAI_API_KEY) in your .env file."
                )
            except AuthenticationError as err:
                return (
                    f"Authentication Failed: Invalid API key for provider '{self.provider}'. "
                    "Please verify your credentials in the .env file."
                )
            except Exception as err:
                return f"Execution Error: An unexpected error occurred while communicating with the model: {err}"

            choice = response.choices[0]
            message = choice.message

            # Clean serialization for Pydantic V2 / Python runtime
            if hasattr(message, 'model_dump'):
                dumped = message.model_dump(exclude_none=True)
            elif isinstance(message, dict):
                dumped = message
            else:
                dumped = {
                    'role': 'assistant',
                    'content': message.content,
                    'tool_calls': [tc.model_dump() if hasattr(tc, 'model_dump') else dict(tc) for tc in (message.tool_calls or [])] or None
                }
            messages.append(dumped)

            if not message.tool_calls:
                return message.content or "No response synthesized."

            for tool_call in message.tool_calls:
                fn_name = tool_call.function.name
                raw_args = tool_call.function.arguments
                fn_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args

                print(f"  [Turn {turn + 1} | Action] {fn_name}({fn_args})")

                if fn_name in TOOL_DISPATCHER:
                    try:
                        result = TOOL_DISPATCHER[fn_name](**fn_args)
                    except Exception as err:
                        result = {"error": f"Tool execution failed: {err}"}
                else:
                    result = {"error": f"Unknown tool requested: {fn_name}"}

                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call.id,
                    "name": fn_name,
                    "content": json.dumps(result),
                })

        return "Agent halted: Maximum reasoning steps exceeded without reaching a final answer."
