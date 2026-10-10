import openai


def status_error_detail(exc: openai.APIStatusError) -> str:
    """LM Studio's own reason for an error response, e.g. a prompt that exceeds the context.

    The SDK unwraps `{"error": ...}`, so `exc.body` is the error itself: a string, or an object
    with a `message`.
    """
    error = exc.body
    if isinstance(error, dict):
        error = error.get("message", error.get("error"))
    if isinstance(error, str) and error.strip():
        return f"LM Studio returned HTTP {exc.status_code}: {error.strip()}"
    return f"LM Studio returned HTTP {exc.status_code}"
