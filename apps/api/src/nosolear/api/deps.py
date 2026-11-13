"""Composition root: wires adapters to the routes."""

import sqlite3
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, cast
from urllib.parse import quote

from fastapi import Depends, Request
from sqlalchemy import Engine

from nosolear.adapters.azure_pa import ADAPTER_VERSION as AZURE_PA_ADAPTER_VERSION
from nosolear.adapters.azure_pa import AzurePronunciationScorer
from nosolear.adapters.azure_pa_probe import AzureCapabilityProbe
from nosolear.adapters.azure_speech import AzureSpeech
from nosolear.adapters.azure_stt import AzureTranscriber
from nosolear.adapters.azure_tts import AzureTts
from nosolear.adapters.claude_coach import ClaudeCoach
from nosolear.adapters.content_files import load_pack
from nosolear.adapters.crisper_whisper import CrisperWhisperTranscriber
from nosolear.adapters.environment import SystemEnvironment
from nosolear.adapters.faster_whisper import FasterWhisperTranscriber
from nosolear.adapters.filesystem_audio_store import FilesystemAudioStore
from nosolear.adapters.local_env import (
    current_platform,
    espeak_ng_path,
    installed_transcribers,
    phone_probe_installed,
)
from nosolear.adapters.mlx_whisper import MlxWhisperTranscriber
from nosolear.adapters.model_specs import (
    FASTER_WHISPER_MODELS,
    MLX_WHISPER_MODELS,
    model_spec_for,
)
from nosolear.adapters.retry import (
    RetryingCoach,
    RetryingPronunciationScorer,
    RetryingSpeechSynthesizer,
    RetryingTranscriber,
)
from nosolear.adapters.system_clock import SystemClock
from nosolear.adapters.thread_pool_runner import ThreadPoolJobRunner
from nosolear.adapters.transcriber_speed_check import TranscriberSpeedCheck
from nosolear.adapters.tts_cache import CachedSynthesizer
from nosolear.adapters.wav2vec2_espeak import Wav2Vec2EspeakProbe
from nosolear.app.analysis_steps import provider_steps
from nosolear.app.calibrate_job import ControlsStep, EvaluateStep, QueueRescoreStep
from nosolear.app.check_readiness import check_readiness
from nosolear.app.run_job import run_job
from nosolear.app.scoring_steps import ExtractStep, RescoreStep, ScoringDeps
from nosolear.app.steps import StepRegistry, current_job_id
from nosolear.budget.compose import compose_paid_port, layers_of
from nosolear.budget.meter import Meter
from nosolear.budget.metered_ports import (
    MeteredCoach,
    MeteredPronunciationScorer,
    MeteredSpeechSynthesizer,
    MeteredTranscriber,
)
from nosolear.domain.budget import Caps, Provider, Unit, period_for
from nosolear.domain.calibration import calibratable_detectors
from nosolear.domain.capabilities import is_stale, real_time_factors
from nosolear.domain.content import SeedContent
from nosolear.domain.extraction.opportunities import tracked_keys
from nosolear.domain.jobs import JobKind
from nosolear.domain.packs import LanguagePack, PackError
from nosolear.domain.readiness import ReadinessReport, UsageSnapshot
from nosolear.domain.speech import ProviderCapabilities
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector, Taxonomy
from nosolear.domain.transcriber_choice import (
    Platform,
    TranscriberChoice,
    TranscriberName,
    choose_transcriber,
)
from nosolear.persistence.baseline_repository import BaselineRepository
from nosolear.persistence.calibration_repository import CalibrationRepository
from nosolear.persistence.capabilities import CapabilityRepository, read_capability_records
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.feedback_repositories import (
    FeedbackRepository,
    SessionJobRepository,
    SessionRepository,
)
from nosolear.persistence.job_queue import SqliteJobQueue
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.persistence.plan_repositories import (
    DailyPlanRepository,
    DailySessionRepository,
    PromptBankRepository,
    ScoringCoverage,
)
from nosolear.persistence.repositories import (
    AnalysisRepository,
    AttemptRepository,
    ObservationRepository,
    ProfileRepository,
    RecheckRepository,
    RecordingRepository,
)
from nosolear.persistence.scoring_repository import (
    ExtractionInputsRepository,
    ExtractionRepository,
    ScoringConfigRepository,
)
from nosolear.persistence.tts_cache import TtsCacheRepository
from nosolear.ports.analyses import AnalysisStore
from nosolear.ports.audio import AttemptReader, AudioStore, RecordingStore
from nosolear.ports.baseline_store import BaselineStore
from nosolear.ports.calibration_store import CalibrationStore
from nosolear.ports.clock import Clock
from nosolear.ports.environment import EnvironmentProbe
from nosolear.ports.feedback import FeedbackStore, SessionJobStatus, SessionReader
from nosolear.ports.jobs import JobQueue
from nosolear.ports.ledger import UsageLedger
from nosolear.ports.plan import (
    DailyPlanStore,
    DailySessionStore,
    PromptBank,
    RecheckStore,
    ScoredKeys,
)
from nosolear.ports.providers import (
    CapabilityProbe,
    Coach,
    PhoneProbe,
    PronunciationScorer,
    SpeechSynthesizer,
    Synthesizer,
    Transcriber,
)
from nosolear.ports.scoring_stores import ExtractionInputs, ScoringConfigReader
from nosolear.settings import Settings

DATABASE_NAME = "nosolear.sqlite"


@dataclass(frozen=True, slots=True)
class RawPorts:
    """A port given here replaces the real raw adapter and is still wrapped as the real one
    would be. `None` builds the real adapter. This is the seam for the eval harness and tests."""

    scorer: PronunciationScorer | None = None
    transcriber: Transcriber | None = None
    speech_synthesizer: SpeechSynthesizer | None = None
    phone_probe: PhoneProbe | None = None
    coach: Coach | None = None


@dataclass(frozen=True, slots=True)
class Providers:
    """Every port a job step calls, each wrapped by its composition layers (ARCHITECTURE.md
    section 11). Building them imports no provider SDK and needs no key."""

    scorer: PronunciationScorer
    transcriber: Transcriber
    transcriber_choice: TranscriberChoice
    phone_probe: PhoneProbe | None
    synthesizer: Synthesizer
    coach: Coach

    def paid_ports(self) -> dict[str, object]:
        """The ports that spend quota. The Azure transcriber is listed only when it is metered."""
        ports: dict[str, object] = {
            "pronunciation_scorer": self.scorer,
            "synthesizer": self.synthesizer,
            "coach": self.coach,
        }
        if "metered" in layers_of(self.transcriber):
            ports["transcriber_azure"] = self.transcriber
        return ports


@dataclass(frozen=True, slots=True)
class Services:
    """Everything the routes and the runner share. Built once per app by `build_services`."""

    audio_store: AudioStore
    jobs: JobQueue
    ledger: UsageLedger
    analyses: AnalysisStore
    registry: StepRegistry
    runner: ThreadPoolJobRunner
    providers: Providers
    clock: Clock
    observations: ObservationRepository
    profiles: ProfileRepository
    recordings: RecordingStore
    attempts: AttemptReader


def get_profile_repository(request: Request) -> ProfileRepository:
    engine = cast(Engine, request.app.state.engine)
    return ProfileRepository(engine, DEFAULT_TAXONOMY)


def load_active_pack(settings: Settings) -> LanguagePack:
    """The configured pack; `PackError` propagates so each caller can report it its own way."""
    return load_pack(settings.packs_dir, settings.pack)


def get_settings(request: Request) -> Settings:
    return cast(Settings, request.app.state.settings)


def get_services(request: Request) -> Services:
    return cast(Services, request.app.state.services)


def get_baseline_store(request: Request) -> BaselineStore:
    engine = cast(Engine, request.app.state.engine)
    return BaselineRepository(engine)


def get_extraction_inputs(request: Request) -> ExtractionInputs:
    engine = cast(Engine, request.app.state.engine)
    return ExtractionInputsRepository(engine)


def get_scoring_configs(request: Request) -> ScoringConfigReader:
    engine = cast(Engine, request.app.state.engine)
    return ScoringConfigRepository(engine, DEFAULT_TAXONOMY)


def get_daily_plan_store(request: Request) -> DailyPlanStore:
    engine = cast(Engine, request.app.state.engine)
    return DailyPlanRepository(engine, DEFAULT_TAXONOMY)


def get_daily_session_store(request: Request) -> DailySessionStore:
    engine = cast(Engine, request.app.state.engine)
    return DailySessionRepository(engine)


def get_prompt_bank(request: Request) -> PromptBank:
    engine = cast(Engine, request.app.state.engine)
    return PromptBankRepository(engine)


def get_scored_keys(request: Request) -> ScoredKeys:
    engine = cast(Engine, request.app.state.engine)
    return ScoringCoverage(ScoringConfigRepository(engine, DEFAULT_TAXONOMY), DEFAULT_TAXONOMY)


def get_recheck_store(request: Request) -> RecheckStore:
    engine = cast(Engine, request.app.state.engine)
    return RecheckRepository(engine)


def get_session_reader(request: Request) -> SessionReader:
    engine = cast(Engine, request.app.state.engine)
    return SessionRepository(engine)


def get_session_jobs(request: Request) -> SessionJobStatus:
    engine = cast(Engine, request.app.state.engine)
    return SessionJobRepository(engine)


def get_feedback_store(request: Request) -> FeedbackStore:
    engine = cast(Engine, request.app.state.engine)
    return FeedbackRepository(engine)


def get_observation_repository(request: Request) -> ObservationRepository:
    engine = cast(Engine, request.app.state.engine)
    return ObservationRepository(engine)


def get_attempt_repository(request: Request) -> AttemptRepository:
    engine = cast(Engine, request.app.state.engine)
    return AttemptRepository(engine)


def get_seed_content(request: Request) -> SeedContent | None:
    """The seed content the app synced at startup, or None when it did not load."""
    return cast(SeedContent | None, request.app.state.seed_content)


def get_providers(request: Request) -> Providers:
    return get_services(request).providers


def get_job_queue(request: Request) -> JobQueue:
    return get_services(request).jobs


def get_clock(request: Request) -> Clock:
    """Every use case reads time through this, so tests can move the clock."""
    return get_services(request).clock


def get_environment() -> EnvironmentProbe:
    return SystemEnvironment()


def get_readiness_report(
    settings: Annotated[Settings, Depends(get_settings)],
    env: Annotated[EnvironmentProbe, Depends(get_environment)],
) -> ReadinessReport:
    """The route's only dependency; tests override it."""
    return check_readiness(
        settings,
        env,
        usage=read_usage(settings),
        capability_records=read_capabilities(settings),
    )


def paid_scorer(
    raw: PronunciationScorer, meter: Meter, *, sleep: Callable[[float], None] = time.sleep
) -> PronunciationScorer:
    """Every attempt is metered, so each retry reserves again: retry -> metered -> raw."""
    return compose_paid_port(
        raw,
        metered=lambda port: MeteredPronunciationScorer(port, meter),
        retry=lambda port: RetryingPronunciationScorer(port, sleep=sleep),
    )


def paid_transcriber(
    raw: Transcriber, meter: Meter, *, sleep: Callable[[float], None] = time.sleep
) -> Transcriber:
    return compose_paid_port(
        raw,
        metered=lambda port: MeteredTranscriber(port, meter),
        retry=lambda port: RetryingTranscriber(port, sleep=sleep),
    )


def paid_speech_synthesizer(
    raw: SpeechSynthesizer,
    meter: Meter,
    *,
    voice: str,
    locale: str,
    sleep: Callable[[float], None] = time.sleep,
) -> SpeechSynthesizer:
    """Retry -> metered -> raw. The clip cache is added outside this stack in Task 11."""
    return compose_paid_port(
        raw,
        metered=lambda port: MeteredSpeechSynthesizer(port, meter, voice=voice, locale=locale),
        retry=lambda port: RetryingSpeechSynthesizer(port, sleep=sleep),
    )


def paid_coach(
    raw: Coach, meter: Meter, *, taxonomy: Taxonomy, sleep: Callable[[float], None] = time.sleep
) -> Coach:
    """Retry -> metered -> raw: every attempt reserves its own upper bound."""
    return compose_paid_port(
        raw,
        metered=lambda port: MeteredCoach(port, meter, taxonomy=taxonomy),
        retry=lambda port: RetryingCoach(port, sleep=sleep),
    )


def _given_or[T](given: T | None, build: Callable[[], T]) -> T:
    return given if given is not None else build()


def _local_transcriber(name: TranscriberName, settings: Settings) -> Transcriber:
    """Local transcribers are neither metered nor retried; their model specs are pinned."""
    if name is TranscriberName.FASTER_WHISPER:
        spec = model_spec_for(FASTER_WHISPER_MODELS, settings.faster_whisper_model)
        return FasterWhisperTranscriber(spec=spec)
    if name is TranscriberName.MLX_WHISPER:
        spec_mlx = model_spec_for(MLX_WHISPER_MODELS, settings.mlx_whisper_model)
        return MlxWhisperTranscriber(spec=spec_mlx)
    return CrisperWhisperTranscriber()


def build_capability_probes(
    settings: Settings, providers: Providers, *, engine: Engine, clock: Clock
) -> tuple[CapabilityProbe, ...]:
    """The live probes `doctor --probe` runs. Azure probes go through the wrapped ports, so a
    probe spends quota like a real attempt. Speed checks run only for transcribers that are
    installed, and `crisper_whisper` only when it is the configured choice (its weights are
    fetched on first use)."""
    probes: list[CapabilityProbe] = [
        AzureCapabilityProbe(
            synthesizer=providers.synthesizer,
            scorer=providers.scorer,
            data_dir=settings.data_dir,
            region=settings.azure_speech_region,
            locale=settings.azure_locale,
            clock=clock,
        )
    ]
    installed = installed_transcribers()
    for name in (
        TranscriberName.MLX_WHISPER,
        TranscriberName.FASTER_WHISPER,
        TranscriberName.CRISPER_WHISPER,
    ):
        if name not in installed:
            continue
        if name is TranscriberName.MLX_WHISPER and current_platform() is not Platform.MACOS_ARM64:
            continue
        if name is TranscriberName.CRISPER_WHISPER and settings.transcriber != name:
            continue
        probes.append(
            TranscriberSpeedCheck(
                name=name,
                synthesizer=providers.synthesizer,
                transcriber=_local_transcriber(name, settings),
                data_dir=settings.data_dir,
                clock=clock,
            )
        )
    return tuple(probes)


def build_providers(
    settings: Settings,
    *,
    engine: Engine,
    ledger: UsageLedger,
    clock: Clock,
    real_time_factors: Mapping[TranscriberName, float] | None = None,
    raw: RawPorts | None = None,
) -> Providers:
    """Every port, composed once. One `Meter` serves every paid port and reads the running job
    id, so each ledger row names its job."""
    ports = raw if raw is not None else RawPorts()
    meter = Meter(ledger, job_id=current_job_id)
    taxonomy = DEFAULT_TAXONOMY
    locale = settings.azure_locale
    speech = AzureSpeech(key=settings.azure_speech_key, region=settings.azure_speech_region)

    scorer = paid_scorer(
        _given_or(ports.scorer, lambda: AzurePronunciationScorer(speech, locale=locale)), meter
    )

    choice = choose_transcriber(
        settings.transcriber,
        platform=current_platform(),
        installed=installed_transcribers(),
        real_time_factors=real_time_factors or {},
    )
    transcriber: Transcriber
    if ports.transcriber is not None:
        transcriber = paid_transcriber(ports.transcriber, meter)
    elif choice.name is TranscriberName.AZURE_STT:
        transcriber = paid_transcriber(AzureTranscriber(speech, locale=locale), meter)
    else:
        transcriber = _local_transcriber(choice.name, settings)

    probe: PhoneProbe | None
    if ports.phone_probe is not None:
        probe = ports.phone_probe
    elif phone_probe_installed() and (espeak := espeak_ng_path()) is not None:
        probe = Wav2Vec2EspeakProbe(espeak=espeak)
    else:
        probe = None

    voice = settings.tts_voice
    raw_tts = _given_or(
        ports.speech_synthesizer, lambda: AzureTts(speech, voice=voice, locale=locale)
    )
    paid_tts = paid_speech_synthesizer(raw_tts, meter, voice=voice, locale=locale)
    synthesizer = CachedSynthesizer(
        paid_tts,
        store=TtsCacheRepository(engine),
        data_dir=settings.data_dir,
        voice=voice,
        clock=clock,
    )

    coach = paid_coach(
        _given_or(
            ports.coach,
            lambda: ClaudeCoach(
                api_key=settings.anthropic_api_key,
                model=settings.coach_model,
                taxonomy=taxonomy,
            ),
        ),
        meter,
        taxonomy=taxonomy,
    )
    return Providers(
        scorer=scorer,
        transcriber=transcriber,
        transcriber_choice=choice,
        phone_probe=probe,
        synthesizer=synthesizer,
        coach=coach,
    )


def build_stand_in_synthesizer(settings: Settings) -> Synthesizer:
    """The metered, cached synthesizer the `stand-in` command uses, on the configured database.
    It is built only for that command, so every other command stays free of provider setup."""
    clock = SystemClock()
    engine = create_engine_for(settings.database_url)
    upgrade_to_head(engine)
    ledger = build_ledger(settings, engine, clock=clock)
    return build_providers(settings, engine=engine, ledger=ledger, clock=clock).synthesizer


def _caps(settings: Settings) -> Caps:
    return Caps.from_hours_chars_tokens(
        azure_audio_hours=settings.cap_azure_audio_hours,
        azure_tts_chars=settings.cap_azure_tts_chars,
        claude_tokens=settings.cap_claude_tokens,
    )


def build_ledger(settings: Settings, engine: Engine, *, clock: Clock | None = None) -> UsageLedger:
    return SqliteUsageLedger(engine, caps=_caps(settings), clock=clock or SystemClock())


def build_services(
    settings: Settings,
    engine: Engine,
    *,
    registry: StepRegistry | None = None,
    clock: Clock | None = None,
    ledger: UsageLedger | None = None,
    raw_ports: RawPorts | None = None,
) -> Services:
    """Wires every adapter and registers the analysis steps. Nothing here touches the database;
    the caller migrates first. A step the caller already registered is kept as it is."""
    clock = clock or SystemClock()
    ledger = ledger if ledger is not None else build_ledger(settings, engine, clock=clock)
    registry = registry if registry is not None else StepRegistry()
    jobs = SqliteJobQueue(engine, clock=clock)
    # The same stored speed figures `doctor` reads, so `auto` picks what the readiness report says.
    speeds = real_time_factors(CapabilityRepository(engine).latest_all())
    providers = build_providers(
        settings,
        engine=engine,
        ledger=ledger,
        clock=clock,
        real_time_factors=speeds,
        raw=raw_ports,
    )
    analyses = AnalysisRepository(engine, clock)
    recordings = RecordingRepository(engine, clock)
    attempts = AttemptRepository(engine)
    audio = FilesystemAudioStore(settings.data_dir)
    configs = ScoringConfigRepository(engine, DEFAULT_TAXONOMY)
    observations = ObservationRepository(engine)
    profiles = ProfileRepository(engine, DEFAULT_TAXONOMY)
    scoring = ScoringDeps(
        inputs=ExtractionInputsRepository(engine),
        configs=configs,
        extractions=ExtractionRepository(engine),
        observations=observations,
        profiles=profiles,
        pack=lambda: load_active_pack(settings),
        taxonomy=DEFAULT_TAXONOMY,
        clock=clock,
        baselines=BaselineRepository(engine),
    )
    for step in provider_steps(
        scorer=providers.scorer,
        transcriber=providers.transcriber,
        phone_probe=providers.phone_probe,
        coach=providers.coach,
        taxonomy=DEFAULT_TAXONOMY,
        analyses=analyses,
        recordings=recordings,
        attempts=attempts,
        audio=audio,
        configs=configs,
        tracked=lambda: _tracked_keys(settings),
    ):
        if registry.get(JobKind.ANALYZE, step.name) is None:
            registry.register(JobKind.ANALYZE, step)
    if registry.get(JobKind.ANALYZE, ExtractStep.name) is None:
        registry.register(JobKind.ANALYZE, ExtractStep(scoring))
    if registry.get(JobKind.RESCORE, RescoreStep.name) is None:
        registry.register(JobKind.RESCORE, RescoreStep(scoring))
    calibration = CalibrationRepository(engine, clock)
    calibrate_steps = (
        ControlsStep(
            store=calibration,
            synthesizer=providers.synthesizer,
            scorer=providers.scorer,
            phone_probe=providers.phone_probe,
            data_dir=settings.data_dir,
        ),
        EvaluateStep(
            store=calibration,
            analyses=analyses,
            capabilities=lambda: _calibration_capabilities(engine, providers),
            clock=clock,
        ),
        QueueRescoreStep(queue=jobs),
    )
    for calibrate_step in calibrate_steps:
        if registry.get(JobKind.CALIBRATE, calibrate_step.name) is None:
            registry.register(JobKind.CALIBRATE, calibrate_step)

    def run(job_id: str) -> object:
        return run_job(job_id=job_id, jobs=jobs, registry=registry)

    return Services(
        audio_store=audio,
        jobs=jobs,
        ledger=ledger,
        analyses=analyses,
        registry=registry,
        runner=ThreadPoolJobRunner(jobs, run, workers=settings.job_workers),
        providers=providers,
        clock=clock,
        observations=observations,
        profiles=profiles,
        recordings=recordings,
        attempts=attempts,
    )


def _calibration_capabilities(engine: Engine, providers: Providers) -> dict[str, object]:
    """What the calibrated config records about the install it was made on."""
    record = CapabilityRepository(engine).latest("azure", "azure_pa")
    azure: dict[str, object] = {}
    if record is not None:
        azure = {
            "nbest_phonemes": record.capabilities.get("nbest_phonemes"),
            "prosody": record.capabilities.get("prosody"),
            "provider_version": record.provider_version,
        }
    return {"azure_pa": azure, "phone_probe": {"ready": providers.phone_probe is not None}}


def get_calibration_store(request: Request) -> CalibrationStore:
    engine = cast(Engine, request.app.state.engine)
    return CalibrationRepository(engine, get_services(request).clock)


def get_available_detectors(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
) -> frozenset[Detector]:
    """The detectors a calibration can use here: Azure only with a fresh n-best capability, the
    phone probe only when it is installed."""
    engine = cast(Engine, request.app.state.engine)
    record = CapabilityRepository(engine).latest("azure", "azure_pa")
    azure_nbest = (
        record is not None
        and not is_stale(
            record,
            region=settings.azure_speech_region,
            locale=settings.azure_locale,
            adapter_version=AZURE_PA_ADAPTER_VERSION,
        )
        and record.capabilities.get("nbest_phonemes") is True
    )
    providers = get_providers(request)
    return calibratable_detectors(
        azure_nbest=azure_nbest,
        phone_probe_ready=providers.phone_probe is not None,
    )


def _tracked_keys(settings: Settings) -> frozenset[str]:
    """Every key the active pack can add, or the taxonomy alone when the pack does not load."""
    try:
        pack = load_active_pack(settings)
    except PackError:
        return frozenset(d.key for d in DEFAULT_TAXONOMY.defined())
    return tracked_keys(DEFAULT_TAXONOMY, pack)


def read_capabilities(settings: Settings) -> tuple[ProviderCapabilities, ...]:
    """The newest capability record per adapter, read without creating or migrating anything.
    Empty when the database file or its table does not exist, or cannot be read."""
    conn = _open_read_only(settings)
    if conn is None:
        return ()
    try:
        return tuple(read_capability_records(conn))
    except sqlite3.Error:
        return ()
    finally:
        conn.close()


def _open_read_only(settings: Settings) -> sqlite3.Connection | None:
    database = settings.data_dir / DATABASE_NAME
    if not database.is_file():
        return None
    # With no `-wal` file the server is stopped, and a plain read-only open of a WAL database would
    # create `-wal` and `-shm`; `immutable=1` reads the file without creating either.
    wal_present = database.with_name(database.name + "-wal").exists()
    mode = "mode=ro" if wal_present else "mode=ro&immutable=1"
    try:
        return sqlite3.connect(f"file:{quote(str(database))}?{mode}", uri=True)
    except sqlite3.Error:
        return None


def read_usage(settings: Settings) -> UsageSnapshot | None:
    """This period's figures from the ledger, opened read-only.

    None when the database file or its `usage_ledger` table does not exist, or when SQLite
    cannot read the file. Never creates, migrates or writes the database (`doctor` stays offline).
    """
    conn = _open_read_only(settings)
    if conn is None:
        return None
    try:
        return _usage_from(conn)
    except sqlite3.Error:
        return None
    finally:
        conn.close()


def _usage_from(conn: sqlite3.Connection) -> UsageSnapshot | None:
    table = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'usage_ledger'"
    ).fetchone()
    if table is None:
        return None
    now = SystemClock().now()
    audio_seconds = _spent(conn, Provider.AZURE, Unit.AUDIO_SECONDS, now)
    tts_chars = _spent(conn, Provider.AZURE, Unit.TTS_CHARS, now)
    claude_tokens = _spent(conn, Provider.ANTHROPIC, Unit.TOKENS, now)
    return UsageSnapshot(
        azure_audio_hours=audio_seconds / 3600,
        tts_chars=tts_chars,
        claude_tokens=claude_tokens,
    )


def _spent(conn: sqlite3.Connection, provider: Provider, unit: Unit, now: datetime) -> int:
    """Recorded actuals plus open reservations for the current period of this provider and unit."""
    period = period_for(provider, unit, now)
    row = conn.execute(
        "SELECT COALESCE(SUM(CASE WHEN state = 'recorded' THEN actual ELSE 0 END), 0) "
        "+ COALESCE(SUM(CASE WHEN state = 'reserved' THEN estimate ELSE 0 END), 0) "
        "FROM usage_ledger WHERE provider = ? AND unit = ? AND period = ?",
        (provider.value, unit.value, period),
    ).fetchone()
    return int(row[0])
