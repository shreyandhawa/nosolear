from dataclasses import replace
from datetime import UTC, datetime

from nosolear.domain.capabilities import (
    CLIP_SECONDS,
    NBEST_PHONEMES,
    PROBE_SENTENCE,
    PROSODY,
    REAL_TIME_FACTOR,
    SPEED_CHECK_PASSAGE,
    capability_rows,
    is_stale,
    real_time_factors,
)
from nosolear.domain.readiness import Component, ReadinessStatus
from nosolear.domain.speech import ProviderCapabilities
from nosolear.domain.transcriber_choice import TranscriberChoice, TranscriberName

S = ReadinessStatus
C = Component
NOW = datetime(2026, 11, 12, 9, 0, tzinfo=UTC)
AUTO_MLX = TranscriberChoice(TranscriberName.MLX_WHISPER, auto=True, skipped=(), warning=None)
AZURE_AUTO = TranscriberChoice(
    TranscriberName.AZURE_STT,
    auto=True,
    skipped=((TranscriberName.FASTER_WHISPER, "not installed"),),
    warning=None,
)


def azure_caps(*, nbest: bool = True, prosody: bool = False, **kw: object) -> ProviderCapabilities:
    values: dict[str, object] = {
        "provider": "azure",
        "adapter": "azure_pa",
        "adapter_version": 1,
        "provider_version": "1.53.0",
        "region": "eastus",
        "locale": "en-US",
        "capabilities": {NBEST_PHONEMES: nbest, PROSODY: prosody},
        "probed_at": NOW,
    } | kw
    return ProviderCapabilities(**values)  # pyright: ignore[reportArgumentType]


def rows(
    *,
    records: tuple[ProviderCapabilities, ...] = (),
    region: str | None = "eastus",
    locale: str | None = "en-US",
    azure_ready: bool = True,
    choice: TranscriberChoice = AUTO_MLX,
    installed: frozenset[TranscriberName] = frozenset({TranscriberName.MLX_WHISPER}),
    factors: dict[TranscriberName, float] | None = None,
    phone: bool = False,
    espeak: bool = False,
    auto_fix: str = "fix",
):
    return capability_rows(
        records=records,
        region=region,
        locale=locale,
        azure_ready=azure_ready,
        transcriber=choice,
        installed=installed,
        real_time_factors=factors or {},
        phone_probe_installed=phone,
        espeak_found=espeak,
        auto_fix=auto_fix,
    )


def row(found, component: Component):
    return next(r for r in found if r.component is component)


def test_capabilities_stale_after_region_or_locale_change():
    caps = azure_caps()
    assert is_stale(caps, region="westeurope", locale="en-US", adapter_version=1)
    assert is_stale(caps, region="eastus", locale="en-GB", adapter_version=1)
    assert is_stale(caps, region="eastus", locale="en-US", adapter_version=2)
    assert not is_stale(caps, region="eastus", locale="en-US", adapter_version=1)


def test_a_stale_record_is_not_probed_with_the_reason():
    r = row(rows(records=(azure_caps(),), region="westeurope"), C.AZURE_CAPABILITIES)
    assert r.status is S.NOT_PROBED
    assert r.reason == (
        "probed with a different region or locale; run `nosolear doctor --probe` again"
    )


def test_both_capabilities_are_ready_with_the_probe_date():
    r = row(rows(records=(azure_caps(prosody=True),)), C.AZURE_CAPABILITIES)
    assert r.status is S.READY
    assert r.reason == "n-best yes, prosody yes (probed 2026-11-12)"


def test_missing_prosody_is_degraded_and_says_why():
    r = row(rows(records=(azure_caps(prosody=False),)), C.AZURE_CAPABILITIES)
    assert r.status is S.DEGRADED
    assert "prosody no: prosody keys can't use azure_pa" in r.reason


def test_no_probe_record_asks_for_the_probe():
    r = row(rows(), C.AZURE_CAPABILITIES)
    assert r.status is S.NOT_PROBED
    assert r.fix == "run `nosolear doctor --probe`"


def test_azure_not_configured_is_not_probed():
    r = row(rows(azure_ready=False), C.AZURE_CAPABILITIES)
    assert r.status is S.NOT_PROBED and r.fix == "configure Azure Speech first"


def test_measured_transcriber_row_text():
    r = row(rows(factors={TranscriberName.MLX_WHISPER: 0.12}), C.TRANSCRIBER)
    assert r.status is S.READY
    assert r.reason == "auto → mlx_whisper (apple extra), 0.12\u00d7 real time"


def test_explicit_slow_transcriber_is_degraded_with_the_choice_warning():
    slow = TranscriberChoice(
        TranscriberName.FASTER_WHISPER,
        auto=False,
        skipped=(),
        warning="slower than 1/3 real time (0.5\u00d7)",
    )
    r = row(
        rows(choice=slow, installed=frozenset({TranscriberName.FASTER_WHISPER})),
        C.TRANSCRIBER,
    )
    assert r.status is S.DEGRADED and "slower than 1/3 real time" in r.reason


def test_auto_fallback_to_azure_is_degraded_with_the_local_fix():
    r = row(
        rows(choice=AZURE_AUTO, installed=frozenset({TranscriberName.AZURE_STT})), C.TRANSCRIBER
    )
    assert r.status is S.DEGRADED
    assert r.fix == ("run `uv sync --extra local` so transcription doesn't spend Azure audio hours")


def test_phone_probe_rows():
    missing_extra = row(rows(phone=False, espeak=True), C.PHONE_PROBE)
    assert missing_extra.status is S.NOT_INSTALLED
    assert missing_extra.fix == "run `uv sync --extra local`, then install espeak-ng"
    missing_espeak = row(rows(phone=True, espeak=False), C.PHONE_PROBE)
    assert missing_espeak.status is S.NOT_INSTALLED
    assert missing_espeak.fix == "install espeak-ng (Homebrew or apt)"
    ready = row(rows(phone=True, espeak=True), C.PHONE_PROBE)
    assert ready.status is S.READY and ready.fix is None


def test_real_time_factors_take_the_latest_local_record_per_adapter():
    older = ProviderCapabilities(
        provider="local",
        adapter="faster_whisper",
        adapter_version=1,
        provider_version="1.2.1",
        region=None,
        locale=None,
        capabilities={REAL_TIME_FACTOR: 0.9, CLIP_SECONDS: 60.0},
        probed_at=datetime(2026, 11, 10, tzinfo=UTC),
    )
    newer = replace(
        older,
        capabilities={REAL_TIME_FACTOR: 0.2, CLIP_SECONDS: 60.0},
        probed_at=datetime(2026, 11, 12, tzinfo=UTC),
    )
    azure = azure_caps()
    assert real_time_factors([older, azure, newer]) == {TranscriberName.FASTER_WHISPER: 0.2}


def test_speed_check_passage_is_about_a_minute_of_speech():
    assert 145 <= len(SPEED_CHECK_PASSAGE.split()) <= 170
    assert "@" not in SPEED_CHECK_PASSAGE and PROBE_SENTENCE.endswith("Thursday.")
