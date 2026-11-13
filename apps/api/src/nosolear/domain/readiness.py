"""What is configured and what is missing, as plain rows. Pure: no I/O, and no key ever enters."""

import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum

from nosolear.domain.speech import ProviderCapabilities
from nosolear.domain.transcriber_choice import (
    Platform,
    TranscriberChoice,
    TranscriberName,
    choose_transcriber,
)


class Component(StrEnum):
    AZURE_SPEECH = "azure_speech"
    AZURE_CAPABILITIES = "azure_capabilities"
    ANTHROPIC = "anthropic"
    TRANSCRIBER = "transcriber"
    PHONE_PROBE = "phone_probe"
    LANGUAGE_PACK = "language_pack"
    DATA_DIR = "data_dir"
    USAGE = "usage"


class ReadinessStatus(StrEnum):
    READY = "ready"
    MISSING = "missing"
    NOT_INSTALLED = "not_installed"
    NOT_PROBED = "not_probed"
    DEGRADED = "degraded"


COMPONENT_LABELS: dict[Component, str] = {
    Component.AZURE_SPEECH: "Azure Speech",
    Component.AZURE_CAPABILITIES: "Azure capabilities",
    Component.ANTHROPIC: "Anthropic",
    Component.TRANSCRIBER: "Transcriber",
    Component.PHONE_PROBE: "Phone probe",
    Component.LANGUAGE_PACK: "Language pack",
    Component.DATA_DIR: "Data dir",
    Component.USAGE: "Usage",
}

LOCAL_FIX = "uv sync --extra local"
APPLE_FIX = "uv sync --extra apple"
AZURE_FIX = "set NOSOLEAR_AZURE_SPEECH_KEY and NOSOLEAR_AZURE_SPEECH_REGION in .env"


@dataclass(frozen=True, slots=True)
class PackStatus:
    pack_id: str
    name: str | None
    hypotheses: int
    problems: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class UsageSnapshot:
    azure_audio_hours: float
    tts_chars: int
    claude_tokens: int


@dataclass(frozen=True, slots=True)
class Caps:
    azure_audio_hours: float
    tts_chars: int
    claude_tokens: int


@dataclass(frozen=True, slots=True)
class ReadinessInputs:
    """Everything the rows need. Keys appear only as booleans."""

    azure_key_set: bool
    azure_region: str | None
    azure_locale: str
    anthropic_key_set: bool
    coach_model: str
    transcriber: str
    modules: frozenset[str]
    espeak_installed: bool
    system: str
    machine: str
    pack: PackStatus
    data_dir: str
    data_dir_mode: int | None
    env_file_mode: int | None
    caps: Caps
    usage: UsageSnapshot | None
    inspect_errors: tuple[str, ...] = ()
    capability_records: tuple[ProviderCapabilities, ...] = ()
    real_time_factors: Mapping[TranscriberName, float] = field(
        default_factory=lambda: dict[TranscriberName, float]()
    )
    transcriber_choice: TranscriberChoice | None = None
    """None derives the choice from the inputs above, the way the runtime does."""


@dataclass(frozen=True, slots=True)
class ReadinessRow:
    component: Component
    status: ReadinessStatus
    reason: str
    fix: str | None


@dataclass(frozen=True, slots=True)
class ReadinessReport:
    rows: tuple[ReadinessRow, ...]

    @property
    def ready(self) -> bool:
        return all(row.status is not ReadinessStatus.MISSING for row in self.rows)


def _row(
    component: Component, status: ReadinessStatus, reason: str, fix: str | None = None
) -> ReadinessRow:
    return ReadinessRow(component, status, reason, fix)


def _azure_ready(i: ReadinessInputs) -> bool:
    return i.azure_key_set and bool(i.azure_region)


def _azure_speech(i: ReadinessInputs) -> ReadinessRow:
    if _azure_ready(i):
        return _row(
            Component.AZURE_SPEECH,
            ReadinessStatus.READY,
            f"key set, region {i.azure_region}, locale {i.azure_locale}",
        )
    missing = [
        n for n, ok in (("key", i.azure_key_set), ("region", bool(i.azure_region))) if not ok
    ]
    return _row(
        Component.AZURE_SPEECH,
        ReadinessStatus.MISSING,
        f"{' and '.join(missing)} not set",
        AZURE_FIX,
    )


def _anthropic(i: ReadinessInputs) -> ReadinessRow:
    if i.anthropic_key_set:
        return _row(Component.ANTHROPIC, ReadinessStatus.READY, f"key set, model {i.coach_model}")
    return _row(
        Component.ANTHROPIC,
        ReadinessStatus.MISSING,
        "key not set",
        "set NOSOLEAR_ANTHROPIC_API_KEY in .env",
    )


def _auto_order(i: ReadinessInputs) -> tuple[str, ...]:
    if i.system == "darwin" and i.machine == "arm64":
        return ("mlx_whisper", "faster_whisper", "azure_stt")
    if i.system == "linux":
        return ("faster_whisper", "azure_stt")
    return ("azure_stt",)


def _auto_fix(i: ReadinessInputs) -> str:
    order = _auto_order(i)
    options = [f"run `{APPLE_FIX}`"] if "mlx_whisper" in order else []
    if "faster_whisper" in order:
        options.append(f"run `{LOCAL_FIX}`")
    options.append(AZURE_FIX)
    return ", or ".join(options)


def _language_pack(i: ReadinessInputs) -> ReadinessRow:
    p = i.pack
    if not p.problems:
        return _row(
            Component.LANGUAGE_PACK,
            ReadinessStatus.READY,
            f"{p.pack_id} ({p.name}), {p.hypotheses} hypotheses",
        )
    prefix = f"pack {p.pack_id}: "
    problems = "; ".join(x.removeprefix(prefix) for x in p.problems)
    return _row(
        Component.LANGUAGE_PACK,
        ReadinessStatus.MISSING,
        f"pack '{p.pack_id}' is invalid: {problems}",
        f"edit content/packs/{p.pack_id}/pack.toml or set NOSOLEAR_PACK",
    )


def _loose(mode: int | None) -> bool:
    return mode is not None and mode & 0o077 != 0


def _data_dir(i: ReadinessInputs) -> ReadinessRow:
    c = Component.DATA_DIR
    if i.inspect_errors:
        return _row(
            c,
            ReadinessStatus.MISSING,
            "; ".join(i.inspect_errors),
            f"make {shlex.quote(i.data_dir)} a directory you own and can open,"
            " and make sure .env is readable",
        )
    reasons: list[str] = []
    fixes: list[str] = []
    if _loose(i.data_dir_mode):
        reasons.append(
            f"{i.data_dir}: group or other users have access (`nosolear serve` tightens it)"
        )
        fixes.append(f"chmod 700 {shlex.quote(i.data_dir)}")
    if _loose(i.env_file_mode):
        reasons.append(".env: group or other users have access")
        fixes.append("chmod 600 .env")
    if reasons:
        return _row(c, ReadinessStatus.DEGRADED, "; ".join(reasons), "; ".join(fixes))
    if i.data_dir_mode is None:
        return _row(c, ReadinessStatus.READY, f"{i.data_dir} will be created on first start")
    return _row(c, ReadinessStatus.READY, f"{i.data_dir} exists, owner-only")


def _count(n: int) -> str:
    return f"{n / 1000:g}k" if n >= 1000 else str(n)


def _usage(i: ReadinessInputs) -> ReadinessRow:
    caps, used = i.caps, i.usage
    if used is None:
        reason = (
            f"caps: Azure {caps.azure_audio_hours:g} h and TTS {_count(caps.tts_chars)} chars"
            f" a month, Claude {_count(caps.claude_tokens)} tokens a day (UTC);"
            " no usage recorded yet"
        )
    else:
        reason = (
            f"Azure {used.azure_audio_hours:g} of {caps.azure_audio_hours:g} h"
            f" and TTS {_count(used.tts_chars)} of {_count(caps.tts_chars)} chars this month,"
            f" Claude {_count(used.claude_tokens)} of {_count(caps.claude_tokens)} tokens today"
        )
    return _row(Component.USAGE, ReadinessStatus.READY, reason)


def _needs(name: str) -> tuple[str, ...]:
    return ("torch", "transformers") if name == "crisper_whisper" else (name,)


def _platform(i: ReadinessInputs) -> Platform:
    if i.system == "darwin" and i.machine == "arm64":
        return Platform.MACOS_ARM64
    if i.system == "linux":
        return Platform.LINUX
    return Platform.OTHER


def _installed(i: ReadinessInputs) -> frozenset[TranscriberName]:
    found = {
        name
        for name in TranscriberName
        if name is not TranscriberName.AZURE_STT
        and all(module in i.modules for module in _needs(name))
    }
    if _azure_ready(i):
        found.add(TranscriberName.AZURE_STT)
    return frozenset(found)


def _choice(i: ReadinessInputs) -> TranscriberChoice:
    if i.transcriber_choice is not None:
        return i.transcriber_choice
    return choose_transcriber(
        i.transcriber,
        platform=_platform(i),
        installed=_installed(i),
        real_time_factors=i.real_time_factors,
    )


def build_readiness(inputs: ReadinessInputs) -> ReadinessReport:
    # Imported here: capabilities.py builds rows from this module's types.
    from nosolear.domain.capabilities import capability_rows

    azure_caps, transcriber, phone = capability_rows(
        records=inputs.capability_records,
        region=inputs.azure_region,
        locale=inputs.azure_locale,
        azure_ready=_azure_ready(inputs),
        transcriber=_choice(inputs),
        installed=_installed(inputs),
        real_time_factors=inputs.real_time_factors,
        phone_probe_installed={"torch", "transformers"} <= inputs.modules,
        espeak_found=inputs.espeak_installed,
        auto_fix=_auto_fix(inputs),
    )
    return ReadinessReport(
        rows=(
            _azure_speech(inputs),
            azure_caps,
            _anthropic(inputs),
            transcriber,
            phone,
            _language_pack(inputs),
            _data_dir(inputs),
            _usage(inputs),
        )
    )


def format_readiness(report: ReadinessReport) -> str:
    label_width = max(len(label) for label in COMPONENT_LABELS.values())
    status_width = max(len(s.value) for s in ReadinessStatus)
    lines: list[str] = []
    for r in report.rows:
        status = r.status.value.replace("_", " ")
        lines.append(
            f"{COMPONENT_LABELS[r.component]:<{label_width}}  {status:<{status_width}}  {r.reason}"
        )
        if r.fix:
            lines.append(f"    fix: {r.fix}")
    return "\n".join(lines)
