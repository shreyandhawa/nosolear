"""SSML for Azure text-to-speech: escaped, validated, and hashed for the clip cache. Pure: no I/O.

The text is user-independent coach or prompt text, but it is still escaped so markup in it can
never add an element, a voice or an audio source (ARCHITECTURE.md section 5.3).
"""

import hashlib
import json
import re
from xml.sax.saxutils import escape

FALLBACK_VOICE = "en-US-AvaNeural"
MAX_TEXT_CHARS = 3000
MAX_RATE_PERCENT = 50

_VOICE = re.compile(r"[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural")
_LOCALE = re.compile(r"[a-z]{2,3}-[A-Z]{2}")
_ENTITIES = {"'": "&apos;", '"': "&quot;", "\r": "&#13;"}
# XML 1.0 forbids C0 controls other than tab, newline and carriage return, and U+FFFE and U+FFFF.
_INVALID_XML = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f￾￿]")


def _clean(text: str) -> str:
    return _INVALID_XML.sub("", text)


def build_ssml(text: str, *, voice: str, locale: str, rate_percent: int = 0) -> str:
    if not _VOICE.fullmatch(voice):
        raise ValueError("voice must look like en-US-JennyNeural")
    if not _LOCALE.fullmatch(locale):
        raise ValueError("locale must look like en-US")
    if not -MAX_RATE_PERCENT <= rate_percent <= MAX_RATE_PERCENT:
        raise ValueError("rate_percent must be between -50 and 50")
    cleaned = _clean(text)
    if not cleaned.strip():
        raise ValueError("text is empty")
    if len(cleaned) > MAX_TEXT_CHARS:
        raise ValueError(f"text is longer than {MAX_TEXT_CHARS} characters")
    body = escape(cleaned, _ENTITIES)
    if rate_percent != 0:
        body = f"<prosody rate='{rate_percent:+d}%'>{body}</prosody>"
    return (
        f"<speak version='1.0' xml:lang='{locale}' "
        "xmlns='http://www.w3.org/2001/10/synthesis'>"
        f"<voice name='{voice}'>{body}</voice></speak>"
    )


def tts_hash(text: str, *, voice: str, rate_percent: int) -> str:
    """The cache key: sha256 of the canonical JSON of what decides the audio."""
    canonical = json.dumps(
        {"rate": rate_percent, "text": text, "voice": voice},
        sort_keys=True,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
