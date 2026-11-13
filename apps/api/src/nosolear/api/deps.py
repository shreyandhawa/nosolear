"""Composition root: wires adapters to the routes."""

import sqlite3
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Annotated, cast
from urllib.parse import quote

from fastapi import Depends, Request
from sqlalchemy import Engine

from nosolear.adapters.content_files import load_pack
from nosolear.adapters.environment import SystemEnvironment
from nosolear.adapters.filesystem_audio_store import FilesystemAudioStore
from nosolear.adapters.retry import RetryingPronunciationScorer, RetryingTranscriber
from nosolear.adapters.system_clock import SystemClock
from nosolear.adapters.thread_pool_runner import ThreadPoolJobRunner
from nosolear.app.check_readiness import check_readiness
from nosolear.app.run_job import run_job
from nosolear.app.steps import StepRegistry
from nosolear.budget.compose import compose_paid_port
from nosolear.budget.meter import Meter
from nosolear.budget.metered_ports import MeteredPronunciationScorer, MeteredTranscriber
from nosolear.domain.budget import Caps, Provider, Unit, period_for
from nosolear.domain.packs import LanguagePack
from nosolear.domain.readiness import ReadinessReport, UsageSnapshot
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.job_queue import SqliteJobQueue
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.persistence.repositories import (
    AnalysisRepository,
    AttemptRepository,
    ObservationRepository,
    ProfileRepository,
    RecordingRepository,
)
from nosolear.ports.analyses import AnalysisStore
from nosolear.ports.audio import AttemptReader, AudioStore, RecordingStore
from nosolear.ports.clock import Clock
from nosolear.ports.environment import EnvironmentProbe
from nosolear.ports.jobs import JobQueue
from nosolear.ports.ledger import UsageLedger
from nosolear.ports.providers import PronunciationScorer, Transcriber
from nosolear.settings import Settings

DATABASE_NAME = "nosolear.sqlite"


@dataclass(frozen=True, slots=True)
class Services:
    """Everything the routes and the runner share. Built once per app by `build_services`."""

    audio_store: AudioStore
    jobs: JobQueue
    ledger: UsageLedger
    analyses: AnalysisStore
    registry: StepRegistry
    runner: ThreadPoolJobRunner
    paid_ports: dict[str, object]
    clock: Clock
    observations: ObservationRepository
    profiles: ProfileRepository
    recordings: RecordingStore
    attempts: AttemptReader
    # 0d replaces paid_ports with providers: Providers.


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
    return check_readiness(settings, env, usage=read_usage(settings))


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


def build_paid_ports(settings: Settings, *, ledger: UsageLedger, clock: Clock) -> dict[str, object]:
    """Every paid port, each built through `compose_paid_port`. Empty until Phase 0d adds them."""
    return {}


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
) -> Services:
    """Wires every adapter. Nothing here touches the database; the caller migrates first."""
    clock = clock or SystemClock()
    ledger = ledger if ledger is not None else build_ledger(settings, engine, clock=clock)
    registry = registry if registry is not None else StepRegistry()
    jobs = SqliteJobQueue(engine, clock=clock)

    def run(job_id: str) -> object:
        return run_job(job_id=job_id, jobs=jobs, registry=registry)

    return Services(
        audio_store=FilesystemAudioStore(settings.data_dir),
        jobs=jobs,
        ledger=ledger,
        analyses=AnalysisRepository(engine, clock),
        registry=registry,
        runner=ThreadPoolJobRunner(jobs, run, workers=settings.job_workers),
        paid_ports=build_paid_ports(settings, ledger=ledger, clock=clock),
        clock=clock,
        observations=ObservationRepository(engine),
        profiles=ProfileRepository(engine, DEFAULT_TAXONOMY),
        recordings=RecordingRepository(engine, clock),
        attempts=AttemptRepository(engine),
    )


def read_usage(settings: Settings) -> UsageSnapshot | None:
    """This period's figures from the ledger, opened read-only.

    None when the database file or its `usage_ledger` table does not exist, or when SQLite
    cannot read the file. Never creates, migrates or writes the database (`doctor` stays offline).
    """
    database = settings.data_dir / DATABASE_NAME
    if not database.is_file():
        return None
    # With no `-wal` file the server is stopped, and a plain read-only open of a WAL database would
    # create `-wal` and `-shm`; `immutable=1` reads the file without creating either.
    wal_present = database.with_name(database.name + "-wal").exists()
    mode = "mode=ro" if wal_present else "mode=ro&immutable=1"
    try:
        conn = sqlite3.connect(f"file:{quote(str(database))}?{mode}", uri=True)
    except sqlite3.Error:
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
