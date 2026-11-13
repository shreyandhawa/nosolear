"""Azure Speech surfaces: the error a rejected request raises, and what a caller can render."""

import traceback
from pathlib import Path

from provider_fakes import FakeSpeechBackend
from pydantic import SecretStr

from nosolear.adapters.azure_speech import AzureSpeech, Cancellation
from nosolear.domain.errors import ProviderUnavailable
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
