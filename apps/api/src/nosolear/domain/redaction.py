"""Removing configured secrets from text. Pure: no I/O and no logging."""

import json
from collections.abc import Iterable
from urllib.parse import quote, quote_plus

REDACTED = "[redacted]"


def _variants(secret: str) -> set[str]:
    """The secret as it appears raw and after the common escapings."""
    return {
        secret,
        quote(secret),
        quote(secret, safe=""),
        quote_plus(secret),
        json.dumps(secret)[1:-1],
        json.dumps(secret, ensure_ascii=False)[1:-1],
        repr(secret)[1:-1],
    }


def scrub(text: str, secrets: Iterable[str]) -> str:
    """Replace every non-empty secret, and its escaped forms, with `REDACTED`; longest first."""
    forms = {form for secret in secrets if secret for form in _variants(secret)}
    for form in sorted(forms, key=len, reverse=True):
        text = text.replace(form, REDACTED)
    return text
