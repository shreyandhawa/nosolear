"""The phone probe's stored payload to a `PhoneProbeResult` (ARCHITECTURE.md section 15). Pure.

The payload is `{"espeak_ipa", "espeak_version", "heard_tokens", "model"}`: espeak-ng's IPA for the
reference text, the espeak version, the phones the recognizer heard, and the model's pinned repo
and revision. Both sides are normalized to Azure's phone set. An unmapped symbol propagates as
`UnmappedSymbol`, so nothing is guessed.
"""

from collections.abc import Sequence
from typing import cast

from nosolear.domain.errors import MalformedProviderResponse
from nosolear.domain.phones import normalize_all, split_espeak_ipa
from nosolear.domain.speech import PhoneProbeResult, RawResult

_MALFORMED = "The phone probe returned a result Nosolear can't read"


def parse_phone_probe(raw: RawResult) -> PhoneProbeResult:
    ipa = raw.payload.get("espeak_ipa")
    heard_tokens = raw.payload.get("heard_tokens")
    if not isinstance(ipa, str) or not isinstance(heard_tokens, list):
        raise MalformedProviderResponse(_MALFORMED)
    if not all(isinstance(token, str) for token in cast("Sequence[object]", heard_tokens)):
        raise MalformedProviderResponse(_MALFORMED)
    expected_words = tuple(tuple(normalize_all(word)) for word in split_espeak_ipa(ipa))
    heard = tuple(normalize_all(cast("list[str]", heard_tokens)))
    return PhoneProbeResult(expected_words=expected_words, heard=heard, raw=raw)
