import json
import logging

import anthropic
import httpx2
import pytest
from pydantic import SecretStr
from security.planted import PLANTED_ANTHROPIC_KEY, PROVIDER_BODY_MARKER, assert_no_leak

from adapters.anthropic_payloads import error_json, message_json
from nosolear.adapters.claude_coach import API_BASE_URL, ClaudeCoach
from nosolear.domain.coach import ANALYZE_MAX_TOKENS, CoachTask, coach_keys
from nosolear.domain.errors import (
    MalformedProviderResponse,
    ProviderUnavailable,
    RequestNotSent,
    RetryableProviderError,
)
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX

KEYS = coach_keys(TAX, CoachTask.QUICK_ANSWERS)
GOOD = json.dumps({"findings": [], "rubric": None, "rewrite": None})


def coach(handler, key: str | None = PLANTED_ANTHROPIC_KEY) -> ClaudeCoach:
    http = anthropic.DefaultHttpxClient(transport=httpx2.MockTransport(handler))
    return ClaudeCoach(
        api_key=SecretStr(key) if key is not None else None,
        model="claude-opus-5-5",
        taxonomy=TAX,
        http_client=http,
    )


def analyze(c: ClaudeCoach):
    return c.analyze(
        task=CoachTask.QUICK_ANSWERS,
        prompt_text="Why?",
        transcript="I go",
        allowed_keys=KEYS,
    )


def test_request_shape_ignores_shell_anthropic_env(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_BASE_URL", "https://evil.example")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "wrong-key")
    monkeypatch.setenv("ANTHROPIC_AUTH_TOKEN", "wrong-token")
    monkeypatch.setenv("ANTHROPIC_PROFILE", "wrong-profile")
    seen: list[httpx2.Request] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.append(req)
        return httpx2.Response(200, json=message_json(GOOD, thinking_first=True))

    analyze(coach(handler))
    req = seen[0]
    body = json.loads(req.content)
    assert req.url.host == "api.anthropic.com"
    # anthropic 2.8.0 sends an explicit api_key as a Bearer token; the shell's token never appears.
    assert req.headers["authorization"] == f"Bearer {PLANTED_ANTHROPIC_KEY}"
    assert "x-api-key" not in req.headers
    assert "wrong-token" not in req.headers["authorization"]
    assert body["model"] == "claude-opus-5-5"
    assert body["max_tokens"] == ANALYZE_MAX_TOKENS
    assert body["output_config"]["format"]["type"] == "json_schema"
    assert not {"thinking", "temperature", "top_p", "top_k", "tool_choice", "tools"} & body.keys()


def test_shell_custom_headers_never_reach_the_request(monkeypatch):
    # The SDK merges ANTHROPIC_CUSTOM_HEADERS over its own headers, Authorization included.
    monkeypatch.setenv(
        "ANTHROPIC_CUSTOM_HEADERS",
        "Authorization: Bearer wrong-token\nX-Gateway-Token: gateway-secret",
    )
    monkeypatch.setenv("ANTHROPIC_OPEN_TELEMETRY_TRACES_CONTENT_MODE", "content")
    seen: list[httpx2.Request] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.append(req)
        return httpx2.Response(200, json=message_json(GOOD, thinking_first=True))

    client = coach(handler)
    analyze(client)
    req = seen[0]
    assert req.headers["authorization"] == f"Bearer {PLANTED_ANTHROPIC_KEY}"
    assert "x-gateway-token" not in req.headers
    assert "gateway-secret" not in str(req.headers)
    assert "wrong-token" not in str(req.headers)
    assert client._client is not None
    assert client._client._open_telemetry["traces"]["enabled"] is False


def test_base_url_is_the_anthropic_endpoint():
    assert API_BASE_URL == "https://api.anthropic.com"


def test_a_429_is_one_request_then_retryable():
    seen: list[httpx2.Request] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.append(req)
        return httpx2.Response(429, json=error_json("rate_limit_error"))

    with pytest.raises(RetryableProviderError) as info:
        analyze(coach(handler))
    assert info.value.safe_message == "Anthropic is rate-limiting requests"
    assert len(seen) == 1  # the SDK's retries are off; our wrapper owns them


@pytest.mark.parametrize("status", [500, 529])
def test_server_errors_are_retryable(status):
    def handler(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(status, json=error_json("overloaded_error"))

    with pytest.raises(RetryableProviderError) as info:
        analyze(coach(handler))
    assert info.value.safe_message == "Anthropic is unavailable"


def test_a_connection_error_is_retryable():
    def handler(req: httpx2.Request) -> httpx2.Response:
        raise httpx2.ConnectError("refused")

    with pytest.raises(RetryableProviderError) as info:
        analyze(coach(handler))
    assert info.value.safe_message == "Couldn't reach Anthropic"


def test_rejected_key_never_leaks(caplog):
    caplog.set_level(logging.DEBUG)
    body = error_json(
        "authentication_error",
        message=f"invalid x-api-key {PLANTED_ANTHROPIC_KEY} {PROVIDER_BODY_MARKER}",
    )

    def handler(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(401, json=body)

    with pytest.raises(ProviderUnavailable) as info:
        analyze(coach(handler))
    assert "NOSOLEAR_ANTHROPIC_API_KEY" in str(info.value)
    assert_no_leak(error=info.value, logs=caplog.text)


def test_an_unknown_model_points_at_the_setting():
    def handler(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(404, json=error_json("not_found_error"))

    with pytest.raises(ProviderUnavailable) as info:
        analyze(coach(handler))
    assert info.value.safe_message == "Anthropic rejected the request; check NOSOLEAR_COACH_MODEL"


def test_other_client_errors_are_a_plain_provider_error():
    def handler(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(403, json=error_json("permission_error"))

    with pytest.raises(ProviderUnavailable) as info:
        analyze(coach(handler))
    assert not isinstance(info.value, RetryableProviderError)
    assert (
        info.value.safe_message
        == "Anthropic rejected the API key; check NOSOLEAR_ANTHROPIC_API_KEY"
    )


def test_refusal_and_cutoff_are_typed():
    def refusal(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=message_json(None, stop_reason="refusal"))

    def cutoff(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=message_json(GOOD, stop_reason="max_tokens"))

    with pytest.raises(ProviderUnavailable) as declined:
        analyze(coach(refusal))
    assert declined.value.safe_message == "The coach declined this request"
    with pytest.raises(ProviderUnavailable) as clipped:
        analyze(coach(cutoff))
    assert clipped.value.safe_message == "The coach's answer was cut off"


def test_non_json_text_is_malformed():
    def handler(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=message_json("not json at all"))

    with pytest.raises(MalformedProviderResponse):
        analyze(coach(handler))


def test_a_reply_without_a_text_block_is_malformed():
    def handler(req: httpx2.Request) -> httpx2.Response:
        return httpx2.Response(200, json=message_json(None, thinking_first=True))

    with pytest.raises(MalformedProviderResponse):
        analyze(coach(handler))


def test_tokens_used_sums_usage_and_the_model_is_the_provider_version():
    def handler(req: httpx2.Request) -> httpx2.Response:
        usage = {
            "input_tokens": 1200,
            "output_tokens": 800,
            "cache_creation_input_tokens": 300,
            "cache_read_input_tokens": 100,
        }
        return httpx2.Response(200, json=message_json(GOOD, usage=usage))

    a = analyze(coach(handler))
    assert a.tokens_used == 2400
    assert a.raw.provider == "anthropic"
    assert a.raw.provider_version == "claude-opus-5-5"


def test_a_missing_key_is_request_not_sent_and_makes_no_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    seen: list[httpx2.Request] = []

    def handler(req: httpx2.Request) -> httpx2.Response:
        seen.append(req)
        return httpx2.Response(200, json=message_json(GOOD))

    with pytest.raises(RequestNotSent) as info:
        analyze(coach(handler, key=None))
    assert "NOSOLEAR_ANTHROPIC_API_KEY" in str(info.value)
    assert seen == []


def test_explain_returns_the_checked_fields():
    def handler(req: httpx2.Request) -> httpx2.Response:
        text = json.dumps({"message": "Use the past tense.", "model_text": "I went"})
        return httpx2.Response(200, json=message_json(text))

    e = coach(handler).explain(error_key="grammar.verb_tense", quote="I go", context="I go")
    assert e.message == "Use the past tense." and e.model_text == "I went"
    assert e.tokens_used == 2000
