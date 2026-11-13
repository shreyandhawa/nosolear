"""Parsers from raw provider payloads to the typed results in `domain/speech.py`. Pure."""

from nosolear.domain.results.azure_pa import parse_azure_pa

__all__ = ["parse_azure_pa"]
