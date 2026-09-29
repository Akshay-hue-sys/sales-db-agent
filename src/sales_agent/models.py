"""Model discovery and selection using the google-genai SDK."""
import os
from google import genai
from dotenv import load_dotenv

load_dotenv()

# Priority tier: prefer fast, modern models with robust function-calling capabilities
MODEL_PRIORITY = [
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-1.5-flash",
    "gemini-1.5-pro",
]

def get_client() -> genai.Client:
    """Instantiate the Gemini client using the environment API key."""
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise ValueError("GEMINI_API_KEY environment variable is missing.")
    return genai.Client(api_key=api_key)

def discover_model(client: genai.Client | None = None) -> str:
    """Query available models and select the best supported candidate for tool use.
    
    Returns:
        The target model name string (e.g., 'gemini-2.5-flash').
    """
    if client is None:
        client = get_client()

    # Retrieve all models available to the authenticated account
    available_models = {
        m.name.replace("models/", ""): m 
        for m in client.models.list()
        if hasattr(m, "supported_actions") and "generateContent" in (m.supported_actions or [])
    }

    # Match against our preferred priority hierarchy
    for preferred in MODEL_PRIORITY:
        if preferred in available_models:
            return preferred

    # If no preferred model is explicitly matched, pick the first supported candidate
    if available_models:
        return next(iter(available_models.keys()))

    # Fallback default if catalog listing is restricted
    return "gemini-2.5-flash"
