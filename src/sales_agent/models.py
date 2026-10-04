"""Lazy client and catalog selection; no model rotation on API failures."""

import time
from enum import StrEnum


class ModelFailure(StrEnum):
    AUTHENTICATION = "AUTHENTICATION"
    PERMISSION = "PERMISSION"
    QUOTA = "QUOTA"
    MODEL_NOT_FOUND = "MODEL_NOT_FOUND"
    TRANSIENT_PROVIDER = "TRANSIENT_PROVIDER"
    PROVIDER_FAILURE = "PROVIDER_FAILURE"
    TIMEOUT = "TIMEOUT"
    INVALID_REQUEST = "INVALID_REQUEST"
    MALFORMED_RESPONSE = "MALFORMED_RESPONSE"
    CONFIGURATION = "CONFIGURATION"


class ModelError(Exception):
    def __init__(self, category):
        self.category = category
        super().__init__(f"Model operation failed: {category}.")


def classify_error(exc):
    from httpx import NetworkError, TimeoutException

    if isinstance(exc, (TimeoutError, TimeoutException)):
        return ModelFailure.TIMEOUT
    if isinstance(exc, NetworkError):
        return ModelFailure.TRANSIENT_PROVIDER
    try:
        code = int(getattr(exc, "code", 0))
    except ValueError, TypeError:
        code = 0
    return {
        400: ModelFailure.INVALID_REQUEST,
        401: ModelFailure.AUTHENTICATION,
        403: ModelFailure.PERMISSION,
        404: ModelFailure.MODEL_NOT_FOUND,
        408: ModelFailure.TIMEOUT,
        429: ModelFailure.QUOTA,
        504: ModelFailure.TIMEOUT,
        500: ModelFailure.TRANSIENT_PROVIDER,
        502: ModelFailure.TRANSIENT_PROVIDER,
        503: ModelFailure.TRANSIENT_PROVIDER,
    }.get(code, ModelFailure.PROVIDER_FAILURE if 500 <= code < 600 else ModelFailure.MALFORMED_RESPONSE)


def get_client(timeout_seconds=15):
    from google import genai
    from google.genai import types

    try:
        return genai.Client(vertexai=False, http_options=types.HttpOptions(timeout=int(timeout_seconds * 1000)))
    except ValueError, TypeError:
        raise ModelError(ModelFailure.CONFIGURATION) from None


def discover_model(client=None, preferred=None, *, deadline=None, clock=time.monotonic):
    from google.genai import types

    if client is None:
        client = get_client()
    deadline = clock() + 15 if deadline is None else deadline
    try:
        remaining = deadline - clock()
        if remaining <= 0:
            raise ModelError(ModelFailure.TIMEOUT)
        iterator = iter(
            client.models.list(
                config=types.ListModelsConfig(
                    page_size=100, http_options=types.HttpOptions(timeout=max(1, int(min(15, remaining) * 1000)))
                )
            )
        )
        available = set()
        for index in range(201):
            if clock() >= deadline:
                raise ModelError(ModelFailure.TIMEOUT)
            try:
                item = next(iterator)
            except StopIteration:
                break
            if index == 200:
                raise ModelError(ModelFailure.CONFIGURATION)
            if "generateContent" in (getattr(item, "supported_actions", None) or []):
                available.add(item.name.removeprefix("models/"))
    except ModelError:
        raise
    except Exception as exc:
        raise ModelError(classify_error(exc)) from None
    if preferred:
        preferred = preferred.removeprefix("models/")
        if preferred not in available:
            raise ModelError(ModelFailure.MODEL_NOT_FOUND)
        return preferred
    # Catalog support is necessary, not proof of tool support. No extra probe.
    candidates = [
        n
        for n in available
        if n.startswith("gemini-")
        and "flash" in n
        and not any(t in n for t in ("image", "audio", "live", "tts", "embedding"))
    ]
    if not candidates:
        raise ModelError(ModelFailure.MODEL_NOT_FOUND)
    return max(candidates)


def generate(client, *, model, contents, config, deadline, clock=time.monotonic, sleep=time.sleep, observer=None):
    for attempt in range(3):
        remaining = deadline - clock()
        if remaining <= 0:
            raise ModelError(ModelFailure.TIMEOUT)
        from google.genai import types

        configured_timeout = getattr(config.http_options, "timeout", None) or 15000
        bounded = config.model_copy(
            update={"http_options": types.HttpOptions(timeout=max(1, min(configured_timeout, int(remaining * 1000))))}
        )
        started = clock()
        try:
            result = client.models.generate_content(model=model, contents=contents, config=bounded)
            if observer:
                observer(model, clock() - started, "SUCCESS")
            return result
        except Exception as exc:
            category = classify_error(exc)
            if observer:
                observer(model, clock() - started, category)
            delay = 2**attempt
            if category != ModelFailure.TRANSIENT_PROVIDER or attempt == 2:
                raise ModelError(category) from None
            if clock() + delay >= deadline:
                raise ModelError(ModelFailure.TIMEOUT) from None
            sleep(delay)
    raise AssertionError("Unreachable")
