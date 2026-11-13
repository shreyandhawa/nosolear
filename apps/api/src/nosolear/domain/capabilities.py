"""What the live probes measured, and the three readiness rows built from it. Pure: no I/O.

A probe stores what the service answered, with the region and locale it answered for. A record
from another region or locale is stale. Speed figures are per local transcriber, and `auto`
honours the latest figure (ARCHITECTURE.md section 4 and section 15).
"""

from collections.abc import Iterable, Mapping, Sequence

from nosolear.domain.readiness import (
    APPLE_FIX,
    AZURE_FIX,
    LOCAL_FIX,
    Component,
    ReadinessRow,
    ReadinessStatus,
)
from nosolear.domain.speech import LOCAL, ProviderCapabilities
from nosolear.domain.transcriber_choice import TranscriberChoice, TranscriberName

NBEST_PHONEMES = "nbest_phonemes"
PROSODY = "prosody"
REAL_TIME_FACTOR = "real_time_factor"
CLIP_SECONDS = "clip_seconds"

AZURE_PROVIDER = "azure"
AZURE_PA_ADAPTER = "azure_pa"
AZURE_PA_VERSION = 1

PROBE_SENTENCE = "The vest and the van were washed with fresh water on Thursday."

SPEED_CHECK_PASSAGE = (
    "Every morning the town market opens before the sun is fully up. Farmers arrive with crates "
    "of apples, carrots and fresh bread, and they set up their stalls along the river path. "
    "Shoppers stroll between the tables, comparing prices and asking how each vegetable was grown. "
    "Some people come for the coffee, which is roasted in a small shop on the corner, and others "
    "come to meet friends before work. By nine o'clock the crowd is busy but relaxed, and the "
    "sound of conversation fills the square. Children chase pigeons near the fountain while their "
    "parents choose flowers for the kitchen table. Later in the day the stalls begin to pack up, "
    "the leftover produce goes to a local food bank, and the square becomes quiet again. Many "
    "residents say the market is the best place to practise talking about everyday things, because "
    "every visitor has a different story to tell and a different way of asking for what they need."
)


def is_stale(
    caps: ProviderCapabilities, *, region: str | None, locale: str | None, adapter_version: int
) -> bool:
    return caps.region != region or caps.locale != locale or caps.adapter_version != adapter_version


def real_time_factors(records: Iterable[ProviderCapabilities]) -> dict[TranscriberName, float]:
    """The latest speed figure per local transcriber. Other records are ignored."""
    latest: dict[str, ProviderCapabilities] = {}
    names = {name.value for name in TranscriberName}
    for record in records:
        if record.provider != LOCAL or record.adapter not in names:
            continue
        held = latest.get(record.adapter)
        if held is None or record.probed_at > held.probed_at:
            latest[record.adapter] = record
    found: dict[TranscriberName, float] = {}
    for adapter, record in latest.items():
        value = record.capabilities.get(REAL_TIME_FACTOR)
        if isinstance(value, int | float) and not isinstance(value, bool):
            found[TranscriberName(adapter)] = float(value)
    return found


def _latest_azure(records: Sequence[ProviderCapabilities]) -> ProviderCapabilities | None:
    matches = [r for r in records if r.provider == AZURE_PROVIDER and r.adapter == AZURE_PA_ADAPTER]
    return max(matches, key=lambda r: r.probed_at) if matches else None


def _azure_row(
    records: Sequence[ProviderCapabilities],
    *,
    region: str | None,
    locale: str | None,
    azure_ready: bool,
) -> ReadinessRow:
    c = Component.AZURE_CAPABILITIES
    if not azure_ready:
        return ReadinessRow(
            c,
            ReadinessStatus.NOT_PROBED,
            "Azure Speech is not configured",
            "configure Azure Speech first",
        )
    record = _latest_azure(records)
    if record is None:
        return ReadinessRow(
            c, ReadinessStatus.NOT_PROBED, "not probed yet", "run `nosolear doctor --probe`"
        )
    if is_stale(record, region=region, locale=locale, adapter_version=AZURE_PA_VERSION):
        return ReadinessRow(
            c,
            ReadinessStatus.NOT_PROBED,
            "probed with a different region or locale; run `nosolear doctor --probe` again",
            None,
        )
    date = record.probed_at.date().isoformat()
    nbest = record.capabilities.get(NBEST_PHONEMES) is True
    prosody = record.capabilities.get(PROSODY) is True
    if nbest and prosody:
        return ReadinessRow(
            c, ReadinessStatus.READY, f"n-best yes, prosody yes (probed {date})", None
        )
    notes: list[str] = []
    if not nbest:
        notes.append("n-best no: substitution keys can't use azure_pa")
    if not prosody:
        notes.append("prosody no: prosody keys can't use azure_pa")
    return ReadinessRow(c, ReadinessStatus.DEGRADED, f"{'; '.join(notes)} (probed {date})", None)


def _factor(value: float) -> str:
    return f"{round(value, 2):g}"


_EXTRA = {
    TranscriberName.MLX_WHISPER: " (apple extra)",
    TranscriberName.FASTER_WHISPER: " (local extra)",
}


def _transcriber_row(
    choice: TranscriberChoice,
    *,
    installed: frozenset[TranscriberName],
    factors: Mapping[TranscriberName, float],
    azure_ready: bool,
    auto_fix: str,
) -> ReadinessRow:
    c = Component.TRANSCRIBER
    name = choice.name
    if name is TranscriberName.AZURE_STT and not azure_ready:
        if choice.auto:
            return ReadinessRow(
                c, ReadinessStatus.MISSING, "no transcriber is usable here", auto_fix
            )
        return ReadinessRow(c, ReadinessStatus.MISSING, "azure_stt needs Azure Speech", AZURE_FIX)
    note = " (non-commercial licence, opt-in)" if name is TranscriberName.CRISPER_WHISPER else ""
    if name not in installed:
        fix = APPLE_FIX if name is TranscriberName.MLX_WHISPER else LOCAL_FIX
        return ReadinessRow(
            c, ReadinessStatus.NOT_INSTALLED, f"{name} library is not installed{note}", fix
        )
    if choice.auto and name is TranscriberName.AZURE_STT and choice.skipped:
        return ReadinessRow(
            c,
            ReadinessStatus.DEGRADED,
            "auto → azure_stt: no local transcriber is usable",
            "run `uv sync --extra local` so transcription doesn't spend Azure audio hours",
        )
    if choice.warning is not None:
        return ReadinessRow(c, ReadinessStatus.DEGRADED, f"{name}: {choice.warning}", None)
    measured = factors.get(name)
    if choice.auto:
        extra = _EXTRA.get(name, "")
        if measured is None:
            reason = f"auto → {name} (speed not yet checked)"
        else:
            reason = f"auto → {name}{extra}, {_factor(measured)}\u00d7 real time"
    else:
        reason = f"{name}{note}"
        if measured is not None:
            reason = f"{name}, {_factor(measured)}\u00d7 real time"
    return ReadinessRow(c, ReadinessStatus.READY, reason, None)


def _phone_row(*, phone_probe_installed: bool, espeak_found: bool) -> ReadinessRow:
    c = Component.PHONE_PROBE
    if phone_probe_installed and espeak_found:
        return ReadinessRow(c, ReadinessStatus.READY, "torch, transformers, espeak-ng", None)
    reason = "optional; needs torch, transformers and espeak-ng"
    if not phone_probe_installed:
        return ReadinessRow(
            c,
            ReadinessStatus.NOT_INSTALLED,
            reason,
            f"run `{LOCAL_FIX}`, then install espeak-ng",
        )
    return ReadinessRow(
        c, ReadinessStatus.NOT_INSTALLED, reason, "install espeak-ng (Homebrew or apt)"
    )


def capability_rows(
    *,
    records: Sequence[ProviderCapabilities],
    region: str | None,
    locale: str | None,
    azure_ready: bool,
    transcriber: TranscriberChoice,
    installed: frozenset[TranscriberName],
    real_time_factors: Mapping[TranscriberName, float],
    phone_probe_installed: bool,
    espeak_found: bool,
    auto_fix: str,
) -> tuple[ReadinessRow, ReadinessRow, ReadinessRow]:
    """The Azure capability, transcriber and phone probe rows, in that order."""
    return (
        _azure_row(records, region=region, locale=locale, azure_ready=azure_ready),
        _transcriber_row(
            transcriber,
            installed=installed,
            factors=real_time_factors,
            azure_ready=azure_ready,
            auto_fix=auto_fix,
        ),
        _phone_row(phone_probe_installed=phone_probe_installed, espeak_found=espeak_found),
    )
