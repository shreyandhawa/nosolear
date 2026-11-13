"""Hand-written Messages API payloads for the coach tests. Shapes follow the API reference;
nothing here is captured from the live service."""

import json
from typing import Any


def usage_json(
    input_tokens: int = 1200,
    output_tokens: int = 800,
    cache_creation: int = 0,
    cache_read: int = 0,
) -> dict[str, Any]:
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "cache_creation_input_tokens": cache_creation,
        "cache_read_input_tokens": cache_read,
        "cache_creation": None,
        "server_tool_use": None,
        "service_tier": "standard",
    }


def message_json(
    text: str | None,
    *,
    thinking_first: bool = False,
    stop_reason: str = "end_turn",
    model: str = "claude-opus-5-5",
    usage: dict[str, Any] | None = None,
) -> dict[str, Any]:
    content: list[dict[str, Any]] = []
    if thinking_first:
        content.append({"type": "thinking", "thinking": "Checking the tense.", "signature": "sig"})
    if text is not None:
        content.append({"type": "text", "text": text, "citations": None})
    return {
        "id": "msg_test_0001",
        "type": "message",
        "role": "assistant",
        "model": model,
        "content": content,
        "stop_reason": stop_reason,
        "stop_sequence": None,
        "usage": usage if usage is not None else usage_json(),
    }


def analysis_text(findings: list[dict[str, Any]] | None = None) -> str:
    return json.dumps({"findings": findings or [], "rubric": None, "rewrite": None})


def error_json(error_type: str, message: str = "request failed") -> dict[str, Any]:
    return {"type": "error", "error": {"type": error_type, "message": message}}
