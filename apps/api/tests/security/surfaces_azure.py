"""Azure Speech surfaces: the error a rejected request raises, and what a caller can render."""

import traceback
from pathlib import Path

from provider_fakes import FakeSpeechBackend
from pydantic import SecretStr

from nosolear.adapters.azure_speech import AzureSpeech, Cancellation
from nosolear.domain.errors import MalformedProviderResponse, ProviderUnavailable
from nosolear.domain.results import parse_azure_pa
from nosolear.domain.speech import RawResult
from security.planted import (
    PLANTED_ANTHROPIC_KEY,
    PLANTED_AZURE_KEY,
    PROVIDER_BODY_MARKER,
    leak_surface,
)


@leak_surface
def azure_cancellation_error(tmp: Path) -> tuple[str, str]:
    """A cancellation whose details hold both planted keys and a provider body marker: the error
    the caller sees, with its traceback, carries only the literal safe message."""
    details = f"bad {PLANTED_AZURE_KEY} {PLANTED_ANTHROPIC_KEY} {PROVIDER_BODY_MARKER}"
    backend = FakeSpeechBackend(cancel=Cancellation("AuthenticationFailure", details))
    speech = AzureSpeech(key=SecretStr(PLANTED_AZURE_KEY), region="eastus", backend=backend)
    try:
        speech.synthesize("<speak/>")
    except ProviderUnavailable as exc:
        rendered = str(exc) + repr(exc) + "".join(traceback.format_exception(exc))
        return "Azure cancellation error and traceback", rendered
    raise AssertionError("a cancelled request did not raise")


@leak_surface
def azure_pa_malformed_error(tmp: Path) -> tuple[str, str]:
    """A pronunciation payload Nosolear cannot read, with both planted keys inside it: the error
    and its traceback carry only the literal sentence."""
    payload: dict[str, object] = {
        "mode": "scripted",
        "reference_text": PLANTED_AZURE_KEY,
        "results": [{"RecognitionStatus": "Success", "echo": PLANTED_ANTHROPIC_KEY}],
    }
    raw = RawResult(
        provider="azure",
        provider_version="1.53.0",
        adapter="azure_pa",
        adapter_version=1,
        payload=payload,
    )
    try:
        parse_azure_pa(raw)
    except MalformedProviderResponse as exc:
        rendered = str(exc) + repr(exc) + "".join(traceback.format_exception(exc))
        return "malformed pronunciation result error and traceback", rendered
    raise AssertionError("a malformed payload did not raise")
