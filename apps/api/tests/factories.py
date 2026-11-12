"""Shared test helpers. Import as `from factories import ...`."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

from sqlalchemy import Engine, text

from nosolear.adapters.content_files import load_pack
from nosolear.domain.observations import Context, Observation, Outcome, make_observation
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY, Detector
from nosolear.settings import CONTENT_DIR, Settings

TAX = DEFAULT_TAXONOMY
NEPALI = load_pack(CONTENT_DIR / "packs", "nepali")
NEUTRAL = load_pack(CONTENT_DIR / "packs", "neutral")
PACK = NEPALI
T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)
DAY = timedelta(days=1)
NOW = T0
NPT = timezone(timedelta(hours=5, minutes=45))


def mk(
    key: str,
    outcome: Outcome,
    at: datetime,
    context: Context = Context.SCRIPTED,
    detector: Detector = Detector.AZURE_PA,
    confidence: float = 1.0,
    evidence: Mapping[str, object] | None = None,
) -> Observation:
    return make_observation(
        taxonomy=TAX,
        error_key=key,
        outcome=outcome,
        detector=detector,
        context=context,
        observed_at=at,
        confidence=confidence,
        evidence=evidence,
    )


SAMPLE_OBS = [
    mk("sound.sub.v.w", Outcome.MISS, T0 - 3 * DAY),
    mk("sound.sub.v.w", Outcome.OK, T0 - 2 * DAY),
    mk("sound.sub.v.w", Outcome.MISS, T0 - DAY, context=Context.UNSCRIPTED),
    mk("sound.sub.θ.t", Outcome.OK, T0 - 2 * DAY),
    mk("sound.sub.θ.t", Outcome.MISS, T0 - DAY),
    mk("fluency.filler", Outcome.MISS, T0 - DAY, detector=Detector.ASR_METRICS, confidence=0.8),
]


def count(engine: Engine, table: str) -> int:
    with engine.connect() as conn:
        return conn.execute(text(f"SELECT COUNT(*) FROM {table}")).scalar_one()


class FixedClock:
    def __init__(self, now: datetime) -> None:
        self._now = now

    def now(self) -> datetime:
        return self._now


def make_settings(**kw: object) -> Settings:
    """Settings that never read a `.env` file; environment variables still apply."""
    return Settings(_env_file=None, **kw)  # pyright: ignore[reportCallIssue,reportArgumentType]


class FakeEnvironment:
    """An `EnvironmentProbe` that reports exactly what it is given."""

    def __init__(
        self,
        modules: Iterable[str] = (),
        executables: Iterable[str] = (),
        modes: Mapping[Path, int] | None = None,
        platform: tuple[str, str] = ("linux", "x86_64"),
    ) -> None:
        self._modules = frozenset(modules)
        self._executables = frozenset(executables)
        self._modes = dict(modes or {})
        self._platform = platform

    def module_available(self, name: str) -> bool:
        return name in self._modules

    def executable_available(self, name: str) -> bool:
        return name in self._executables

    def path_mode(self, path: Path) -> int | None:
        return self._modes.get(path)

    def platform(self) -> tuple[str, str]:
        return self._platform
