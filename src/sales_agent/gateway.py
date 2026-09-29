"""Universal Model Gateway supporting dynamic multi-provider discovery (Gemini, OpenAI, Claude)."""
import os
from typing import Tuple, Dict, Any

# Map providers to active, non-deprecated production endpoints.
PROVIDER_CONFIG: Dict[str, Dict[str, Any]] = {
    "GEMINI_API_KEY": {
        "provider": "gemini",
        "default_model": "gemini/gemini-3.5-flash-lite",
        "prefix": "gemini/",
    },
    "OPENAI_API_KEY": {
        "provider": "openai",
        "default_model": "gpt-4o-mini",
        "prefix": "",
    },
    "ANTHROPIC_API_KEY": {
        "provider": "anthropic",
        "default_model": "claude-3-5-haiku-latest",
        "prefix": "anthropic/",
    },
}

def resolve_provider_and_model(user_model_override: str | None = None) -> Tuple[str, str]:
    """Dynamically negotiates the provider and target model based on environment keys.

    Args:
        user_model_override: Optional user-supplied model name.

    Returns:
        Tuple[str, str]: (provider_name, fully_qualified_litellm_model_identifier)

    Raises:
        RuntimeError: If no supported API key is detected in the environment.
    """
    detected_provider = None
    detected_config = None

    for env_var, config in PROVIDER_CONFIG.items():
        if os.environ.get(env_var):
            detected_provider = config["provider"]
            detected_config = config
            break

    if not detected_provider:
        raise RuntimeError(
            "No supported LLM API key detected in your environment or .env file.\n"
            "Please configure at least one of:\n"
            "  - GEMINI_API_KEY     (Google Gemini)\n"
            "  - OPENAI_API_KEY     (OpenAI GPT)\n"
            "  - ANTHROPIC_API_KEY  (Anthropic Claude)"
        )

    if user_model_override:
        model = user_model_override.strip()
        prefix = detected_config["prefix"]
        if prefix and not model.startswith(prefix):
            model = f"{prefix}{model}"
        return detected_provider, model

    return detected_provider, detected_config["default_model"]
