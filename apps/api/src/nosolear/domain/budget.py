"""Usage caps and period arithmetic for the ledger. Pure: no I/O, no clock reads.

Azure caps reset per UTC calendar month and Claude caps per UTC day (ARCHITECTURE.md section 11).
"""

import math
from dataclasses import dataclass
from datetime import UTC, datetime
from enum import StrEnum


class Provider(StrEnum):
    AZURE = "azure"
    ANTHROPIC = "anthropic"


class Unit(StrEnum):
    AUDIO_SECONDS = "audio_seconds"
    TTS_CHARS = "tts_chars"
    TOKENS = "tokens"


@dataclass(frozen=True, slots=True)
class Caps:
    azure_audio_seconds: int  # monthly
    azure_tts_chars: int  # monthly
    claude_tokens: int  # daily

    @classmethod
    def from_hours_chars_tokens(
        cls, *, azure_audio_hours: float, azure_tts_chars: int, claude_tokens: int
    ) -> Caps:
        return cls(
            azure_audio_seconds=math.floor(azure_audio_hours * 3600),
            azure_tts_chars=azure_tts_chars,
            claude_tokens=claude_tokens,
        )

    def limit(self, provider: Provider, unit: Unit) -> int:
        if provider is Provider.AZURE and unit is Unit.AUDIO_SECONDS:
            return self.azure_audio_seconds
        if provider is Provider.AZURE and unit is Unit.TTS_CHARS:
            return self.azure_tts_chars
        if provider is Provider.ANTHROPIC and unit is Unit.TOKENS:
            return self.claude_tokens
        raise ValueError(f"no cap for {provider.value} {unit.value}")


DEFAULT_CAPS = Caps.from_hours_chars_tokens(
    azure_audio_hours=4.5, azure_tts_chars=450_000, claude_tokens=100_000
)


def period_for(provider: Provider, unit: Unit, now: datetime) -> str:
    """The UTC period a usage row belongs to: `YYYY-MM` for Azure, `YYYY-MM-DD` for Claude."""
    if now.tzinfo is None or now.utcoffset() is None:
        raise ValueError("datetime must be timezone-aware")
    utc = now.astimezone(UTC)
    if provider is Provider.AZURE:
        return utc.strftime("%Y-%m")
    return utc.strftime("%Y-%m-%d")


def fits(cap: int, recorded: int, reserved: int, estimate: int) -> bool:
    return recorded + reserved + estimate <= cap


def ceil_seconds(seconds: float) -> int:
    return max(0, math.ceil(seconds))


@dataclass(frozen=True, slots=True)
class Usage:
    provider: Provider
    unit: Unit
    period: str
    recorded: int
    reserved: int
    cap: int
