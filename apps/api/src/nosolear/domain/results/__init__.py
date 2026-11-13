"""Parsers from raw provider payloads to the typed results in `domain/speech.py`. Pure."""

from nosolear.domain.results.azure_pa import parse_azure_pa
from nosolear.domain.results.azure_stt import parse_azure_stt

__all__ = ["parse_azure_pa", "parse_azure_stt"]
