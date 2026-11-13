"""The Claude coach: the raw `Coach` port over the Messages API (ARCHITECTURE.md section 5.3).

Structured output: `output_config` carries the JSON schema, so the reply is a JSON text block.
The SDK's own retries are off (`max_retries=0`): the retry wrapper owns them. Environment
variables are not read for credentials or the base URL, because both are passed explicitly.
Every failure is raised `from None` with a literal safe message; provider bodies never reach
an error or a log.
"""

from collections.abc import Sequence
from typing import Any, cast

import anthropic
from pydantic import SecretStr

from nosolear.domain.coach import (
    CoachAnalysis,
    CoachExplanation,
    CoachRequest,
    CoachTask,
    analysis_request,
    decode_json_object,
    explanation_request,
    first_text,
    parse_coach_analysis,
    parse_explanation,
    tokens_used_of,
)
from nosolear.domain.errors import (
    ProviderUnavailable,
    RequestNotSent,
    RetryableProviderError,
)
from nosolear.domain.speech import RawResult
from nosolear.domain.taxonomy import Taxonomy

ADAPTER = "claude_coach"
ADAPTER_VERSION = 1
API_BASE_URL = "https://api.anthropic.com"
PROVIDER = "anthropic"
_NOT_CONFIGURED = "Anthropic isn't configured: set NOSOLEAR_ANTHROPIC_API_KEY in .env"


class ClaudeCoach:
    layer = "raw"

    def __init__(
        self,
        *,
        api_key: SecretStr | None,
        model: str,
        taxonomy: Taxonomy,
        http_client: anthropic.DefaultHttpxClient | None = None,
        timeout_s: float = 300.0,
    ) -> None:
        self._model = model
        self._taxonomy = taxonomy
        # Built only with a key: without one the SDK would fall back to the shell's variables.
        self._client: anthropic.Anthropic | None = None
        if api_key is not None:
            client = anthropic.Anthropic(
                api_key=api_key.get_secret_value(),
                base_url=API_BASE_URL,
                max_retries=0,
                timeout=timeout_s,
                http_client=http_client,
                # An explicit option stops the SDK reading ANTHROPIC_OPEN_TELEMETRY* (content capture).
                open_telemetry=False,
            )
            # The SDK reads ANTHROPIC_CUSTOM_HEADERS while it builds the client, and its headers
            # win over the SDK's own Authorization. The SDK offers no way to decline that read, so
            # clear the layer: this client sends no custom headers of its own.
            client._custom_headers = {}  # pyright: ignore[reportPrivateUsage]
            self._client = client

    def analyze(
        self,
        *,
        task: CoachTask,
        prompt_text: str,
        transcript: str,
        allowed_keys: Sequence[str],
    ) -> CoachAnalysis:
        request = analysis_request(
            task=task,
            prompt_text=prompt_text,
            transcript=transcript,
            allowed_keys=allowed_keys,
            taxonomy=self._taxonomy,
        )
        payload = self._send(request)
        return parse_coach_analysis(
            self._raw(payload), transcript=transcript, allowed_keys=allowed_keys
        )

    def explain(self, *, error_key: str, quote: str, context: str) -> CoachExplanation:
        request = explanation_request(
            error_key=error_key, quote=quote, context=context, taxonomy=self._taxonomy
        )
        payload = self._send(request)
        decoded = decode_json_object(first_text(payload))
        return parse_explanation(
            decoded, raw=self._raw(payload), tokens_used=tokens_used_of(payload)
        )

    def _raw(self, payload: dict[str, object]) -> RawResult:
        return RawResult(
            provider=PROVIDER,
            provider_version=str(payload.get("model", self._model)),
            adapter=ADAPTER,
            adapter_version=ADAPTER_VERSION,
            payload=payload,
        )

    def _send(self, request: CoachRequest) -> dict[str, object]:
        if self._client is None:
            raise RequestNotSent(_NOT_CONFIGURED) from None
        try:
            response = self._client.messages.create(
                model=self._model,
                max_tokens=request.max_tokens,
                system=request.system,
                messages=[{"role": "user", "content": request.user}],
                output_config=cast(
                    Any, {"format": {"type": "json_schema", "schema": dict(request.schema)}}
                ),
            )
        except anthropic.RateLimitError:
            raise RetryableProviderError("Anthropic is rate-limiting requests") from None
        except anthropic.InternalServerError:
            raise RetryableProviderError("Anthropic is unavailable") from None
        except anthropic.APIConnectionError:
            raise RetryableProviderError("Couldn't reach Anthropic") from None
        except anthropic.AuthenticationError, anthropic.PermissionDeniedError:
            raise ProviderUnavailable(
                "Anthropic rejected the API key; check NOSOLEAR_ANTHROPIC_API_KEY"
            ) from None
        except anthropic.NotFoundError, anthropic.BadRequestError:
            raise ProviderUnavailable(
                "Anthropic rejected the request; check NOSOLEAR_COACH_MODEL"
            ) from None
        except anthropic.APIStatusError as exc:
            if exc.status_code >= 500:
                raise RetryableProviderError("Anthropic is unavailable") from None
            raise ProviderUnavailable("Anthropic returned an error") from None
        except anthropic.APIError:
            raise ProviderUnavailable("Anthropic returned an error") from None
        payload = cast(dict[str, object], response.model_dump(mode="json"))
        if payload.get("stop_reason") == "refusal":
            raise ProviderUnavailable("The coach declined this request") from None
        if payload.get("stop_reason") == "max_tokens":
            raise ProviderUnavailable("The coach's answer was cut off") from None
        return payload
