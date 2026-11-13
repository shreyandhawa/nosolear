"""Parsers from raw provider payloads to the typed results in `domain/speech.py`. Pure."""

from nosolear.domain.coach import parse_coach_analysis
from nosolear.domain.results.azure_pa import parse_azure_pa
from nosolear.domain.results.azure_stt import parse_azure_stt
from nosolear.domain.results.phone_probe import parse_phone_probe
from nosolear.domain.results.whisper import parse_local_transcript
from nosolear.domain.speech import RawResult, Transcript

LOCAL_TRANSCRIBER_ADAPTERS = frozenset({"faster_whisper", "mlx_whisper", "crisper_whisper"})


def parse_transcript(raw: RawResult) -> Transcript:
    """The transcript for a stored payload, chosen by the adapter that wrote it."""
    if raw.adapter == "azure_stt":
        return parse_azure_stt(raw)
    if raw.adapter in LOCAL_TRANSCRIBER_ADAPTERS:
        return parse_local_transcript(raw)
    raise ValueError(f"no transcript parser for adapter {raw.adapter!r}")


__all__ = [
    "parse_azure_pa",
    "parse_azure_stt",
    "parse_coach_analysis",
    "parse_local_transcript",
    "parse_phone_probe",
    "parse_transcript",
]
