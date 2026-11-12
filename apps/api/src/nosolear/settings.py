import ipaddress
import logging
import os
from pathlib import Path
from typing import Annotated, Literal, get_args
from urllib.parse import urlsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, SecretStr, ValidationError, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

REPO_ROOT = Path(__file__).resolve().parents[4]
CONTENT_DIR = REPO_ROOT / "content"  # packs, calibration items and (0e) the baseline protocol
LOOPBACK_NAMES = frozenset({"localhost", "127.0.0.1", "::1"})
MIN_KEY_LENGTH = 16  # shorter keys are refused, so scrubbing never shreds ordinary text

Transcriber = Literal["auto", "mlx_whisper", "faster_whisper", "azure_stt", "crisper_whisper"]
TRANSCRIBERS: tuple[str, ...] = get_args(Transcriber)

_log = logging.getLogger(__name__)

_LOCALTIME = Path("/etc/localtime")
_MODEL_ID = r"^[A-Za-z0-9._-]+$"


def _loads(name: str) -> bool:
    try:
        ZoneInfo(name)
    except ZoneInfoNotFoundError, ValueError, OSError:
        return False
    return True


def _utc_fallback() -> str:
    _log.warning(
        "could not determine this machine's timezone; using UTC. Set NOSOLEAR_TIMEZONE to an IANA"
        " name such as Asia/Kathmandu"
    )
    return "UTC"


def _local_zone_name() -> str:
    """The machine's IANA zone: `TZ`, else the `/etc/localtime` link target, else UTC."""
    tz = os.environ.get("TZ", "").lstrip(":")
    if tz and _loads(tz):
        return tz
    try:
        parts = Path(os.readlink(_LOCALTIME)).parts
    except OSError:
        return _utc_fallback()
    if "zoneinfo" in parts:
        name = "/".join(parts[len(parts) - parts[::-1].index("zoneinfo") :])
        if name and _loads(name):
            return name
    return _utc_fallback()


def _canonical_origin(origin: str) -> str:
    try:
        parts = urlsplit(origin)
        host, port = parts.hostname, parts.port
    except ValueError as exc:
        raise ValueError("not a valid origin") from exc
    if port == 0:
        raise ValueError("not a valid origin")
    if (
        parts.scheme not in ("http", "https")
        or parts.username is not None
        or parts.password is not None
        or parts.path not in ("", "/")
        or parts.query
        or parts.fragment
        or host not in LOOPBACK_NAMES
    ):
        raise ValueError(
            "every origin must be http(s)://<localhost, 127.0.0.1 or [::1]>[:port] with no path;"
            " token mode is not available until Phase 6"
        )
    shown = f"[{host}]" if ":" in host else host
    if port == {"http": 80, "https": 443}[parts.scheme]:
        port = None  # browsers omit the default port from `Origin`
    return f"{parts.scheme}://{shown}" + (f":{port}" if port is not None else "")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="NOSOLEAR_",
        env_file=REPO_ROOT / ".env",
        extra="ignore",
        env_ignore_empty=True,
        hide_input_in_errors=True,
        validate_default=True,
    )

    data_dir: Path = REPO_ROOT / "data"
    host: str = "127.0.0.1"
    port: int = Field(default=8000, ge=1, le=65535)
    app_origins: Annotated[tuple[str, ...], NoDecode] = (
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    )
    azure_speech_key: SecretStr | None = None
    azure_speech_region: str | None = Field(default=None, pattern=r"^[a-z0-9]+$")
    azure_locale: str = Field(default="en-US", pattern=r"^[a-z]{2,3}-[A-Z]{2}$")
    tts_voice: str = Field(
        default="en-US-JennyNeural", pattern=r"^[a-z]{2,3}-[A-Z]{2}-[A-Za-z]+Neural$"
    )
    anthropic_api_key: SecretStr | None = None
    coach_model: str = Field(default="claude-opus-5-5", pattern=_MODEL_ID)
    transcriber: Literal[
        "auto", "mlx_whisper", "faster_whisper", "azure_stt", "crisper_whisper"
    ] = "auto"
    faster_whisper_model: str = Field(default="small.en", pattern=_MODEL_ID)
    mlx_whisper_model: str = Field(default="whisper-large-v3-turbo", pattern=_MODEL_ID)
    pack: str = Field(default="neutral", pattern=r"^[a-z0-9_]+$")
    timezone: str = Field(default_factory=lambda: _local_zone_name())
    cap_azure_audio_hours: float = Field(default=4.5, gt=0, allow_inf_nan=False)
    cap_azure_tts_chars: int = Field(default=450000, gt=0)
    cap_claude_tokens: int = Field(default=100000, gt=0)
    job_workers: int = Field(default=1, ge=1)

    @field_validator("data_dir")
    @classmethod
    def _resolve_against_repo_root(cls, value: Path) -> Path:
        """A relative path means relative to the repo, so every process agrees on one database."""
        return value if value.is_absolute() else REPO_ROOT / value

    @field_validator("host")
    @classmethod
    def _loopback_only(cls, value: str) -> str:
        try:
            loopback = ipaddress.ip_address(value).is_loopback
        except ValueError:
            loopback = value == "localhost"
        if not loopback:
            raise ValueError("must be a loopback address (127.0.0.1, ::1 or localhost)")
        return value

    @field_validator("app_origins", mode="before")
    @classmethod
    def _split_origins(cls, value: object) -> object:
        if isinstance(value, str):
            return [part.strip() for part in value.split(",") if part.strip()]
        return value

    @field_validator("app_origins")
    @classmethod
    def _loopback_origins(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        if not value:
            raise ValueError("at least one origin is required")
        return tuple(dict.fromkeys(_canonical_origin(origin) for origin in value))

    @field_validator("azure_speech_key", "anthropic_api_key")
    @classmethod
    def _key_long_enough(cls, value: SecretStr | None) -> SecretStr | None:
        if value is None:
            return value
        key = value.get_secret_value()
        if len(key) < MIN_KEY_LENGTH:
            raise ValueError("too short to be a real key")
        if any(ch.isspace() for ch in key):
            raise ValueError("must not contain whitespace (check for a stray space or newline)")
        return value

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str) -> str:
        if not _loads(value):
            if not _loads("UTC"):
                raise ValueError("no timezone database was found; install tzdata")
            raise ValueError("not an IANA timezone name such as Asia/Kathmandu")
        return value

    def secret_values(self) -> tuple[str, ...]:
        keys = (self.azure_speech_key, self.anthropic_api_key)
        return tuple(k.get_secret_value() for k in keys if k and k.get_secret_value())

    @property
    def tzinfo(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    @property
    def packs_dir(self) -> Path:
        return CONTENT_DIR / "packs"

    @property
    def database_url(self) -> str:
        return f"sqlite:///{self.data_dir / 'nosolear.sqlite'}"


def settings_error_summary(exc: ValidationError) -> str:
    """One `NOSOLEAR_<FIELD>: <message>` line per error; never the input value."""
    return "\n".join(
        f"NOSOLEAR_{str(err['loc'][0] if err['loc'] else 'settings').upper()}: {err['msg']}"
        for err in exc.errors(include_input=False, include_url=False, include_context=False)
    )
