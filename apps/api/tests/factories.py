"""Shared test helpers. Import as `from factories import ...`."""

from collections.abc import Iterable, Mapping
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import Engine, text

from nosolear.adapters.content_files import load_pack
from nosolear.domain.coach import CoachAnalysis, CoachFinding, Rubric
from nosolear.domain.estimates import BetaState, estimate
from nosolear.domain.observations import Context, Observation, Outcome, make_observation
from nosolear.domain.packs import LanguagePack
from nosolear.domain.profile import ALGO_VERSION, DEFAULT_CONFIG, Profile, ProfileEntry
from nosolear.domain.speech import (
    NBestPhoneme,
    PhonemeAssessment,
    PhoneProbeResult,
    PronunciationAssessment,
    ProsodyFeedback,
    RawResult,
    ScoringMode,
    Transcript,
    WordAssessment,
    WordTiming,
)
from nosolear.domain.status import Status
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
    attempt_id: str | None = None,
    scoring_config_id: str = "v0",
    provisional: bool = False,
) -> Observation:
    return make_observation(
        taxonomy=TAX,
        error_key=key,
        outcome=outcome,
        detector=detector,
        context=context,
        observed_at=at,
        confidence=confidence,
        attempt_id=attempt_id,
        evidence=evidence,
        scoring_config_id=scoring_config_id,
        provisional=provisional,
    )


SAMPLE_OBS = [
    mk("sound.sub.v.w", Outcome.MISS, T0 - 3 * DAY),
    mk("sound.sub.v.w", Outcome.OK, T0 - 2 * DAY),
    mk("sound.sub.v.w", Outcome.MISS, T0 - DAY, context=Context.UNSCRIPTED),
    mk("sound.sub.θ.t", Outcome.OK, T0 - 2 * DAY),
    mk("sound.sub.θ.t", Outcome.MISS, T0 - DAY),
    mk("fluency.filler", Outcome.MISS, T0 - DAY, detector=Detector.ASR_METRICS, confidence=0.8),
]


def insert_job(engine: Engine, job_id: str) -> None:
    """Jobs have no queue yet, so the foreign key target is inserted directly."""
    stamp = "2026-11-12T08:00:00.000000+00:00"
    with engine.begin() as conn:
        conn.execute(
            text(
                "INSERT INTO jobs (id, kind, attempt_id, status, step, progress, steps_json, "
                "tries, created_at, updated_at) VALUES (:id, 'analyze', NULL, 'queued', NULL, "
                "0.0, '[]', 0, :stamp, :stamp)"
            ),
            {"id": job_id, "stamp": stamp},
        )


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
        raises: Mapping[Path, OSError] | None = None,
    ) -> None:
        self._modules = frozenset(modules)
        self._executables = frozenset(executables)
        self._modes = dict(modes or {})
        self._platform = platform
        self._raises = dict(raises or {})

    def module_available(self, name: str) -> bool:
        return name in self._modules

    def executable_available(self, name: str) -> bool:
        return name in self._executables

    def path_mode(self, path: Path) -> int | None:
        if path in self._raises:
            raise self._raises[path]
        return self._modes.get(path)

    def platform(self) -> tuple[str, str]:
        return self._platform


def loopback_client(app: FastAPI, *, port: int = 8000, **kwargs: Any) -> TestClient:
    """A client the request guard accepts: loopback peer, loopback Host.

    Extra keyword arguments (e.g. `raise_server_exceptions=False`) go to `TestClient`.
    """
    return TestClient(
        app, base_url=f"http://127.0.0.1:{port}", client=("127.0.0.1", 50000), **kwargs
    )


RAW_PA = RawResult("azure", "test", "azure_pa", 1, {})
RAW_PROBE = RawResult("local", "test", "phone_probe", 1, {})


def pa_phone(
    phone: str, accuracy: float, nbest: Iterable[tuple[str, float]] = ()
) -> PhonemeAssessment:
    return PhonemeAssessment(
        phoneme=phone,
        accuracy=accuracy,
        nbest=tuple(NBestPhoneme(p, s) for p, s in nbest),
        start_ms=None,
        end_ms=None,
    )


def pa_word(
    text: str,
    phones: Iterable[PhonemeAssessment],
    error_type: str = "None",
    prosody: Iterable[str] = (),
    start_ms: int | None = 100,
    end_ms: int | None = 520,
) -> WordAssessment:
    error_types = tuple(prosody)
    feedback = ProsodyFeedback(error_types, None, None, None) if error_types else None
    return WordAssessment(
        word=text,
        accuracy=None,
        error_type=error_type,
        start_ms=start_ms,
        end_ms=end_ms,
        phonemes=tuple(phones),
        prosody=feedback,
    )


def pa_result(
    words: Iterable[WordAssessment], has_nbest: bool = True, has_prosody: bool = True
) -> PronunciationAssessment:
    return PronunciationAssessment(
        mode=ScoringMode.SCRIPTED,
        words=tuple(words),
        accuracy=None,
        fluency=None,
        completeness=None,
        prosody=None,
        has_nbest=has_nbest,
        has_prosody=has_prosody,
        raw=RAW_PA,
    )


def probe_result(
    reference_text: str | None,
    expected_words: Iterable[Iterable[str]],
    heard: Iterable[str],
) -> PhoneProbeResult:
    """The probe result for a reference text. The text is not stored on the result; callers pass
    it to the extraction again, so it is accepted here only to read like the call site."""
    del reference_text
    return PhoneProbeResult(
        expected_words=tuple(tuple(word) for word in expected_words),
        heard=tuple(heard),
        raw=RAW_PROBE,
    )


RAW_STT = RawResult("local", "test", "faster_whisper", 1, {})
RAW_COACH = RawResult("anthropic", "test", "claude_coach", 1, {})


def transcript(*words: tuple[str, int, int], fillers_kept: bool = True) -> Transcript:
    """A transcript from (text, start_ms, end_ms) triples."""
    timings = tuple(WordTiming(text, start, end) for text, start, end in words)
    return Transcript(
        text=" ".join(w.text for w in timings),
        words=timings,
        fillers_kept=fillers_kept,
        raw=RAW_STT,
    )


def transcript_from(text: str) -> Transcript:
    """Each whitespace token is a word, 400 ms long, back to back from 0 ms."""
    words = tuple(WordTiming(piece, 400 * i, 400 * i + 400) for i, piece in enumerate(text.split()))
    return Transcript(text=text, words=words, fillers_kept=True, raw=RAW_STT)


def finding(error_key: str, quote: str | None) -> CoachFinding:
    return CoachFinding(
        error_key=error_key,
        quote=quote,
        correction="Say it another way.",
        explanation="A short reason.",
    )


def coach_analysis(findings: Iterable[CoachFinding], rubric: Rubric | None = None) -> CoachAnalysis:
    return CoachAnalysis(
        findings=tuple(findings),
        rubric=rubric,
        rewrite=None,
        dropped=0,
        tokens_used=0,
        raw=RAW_COACH,
    )


def entry(
    key: str,
    *,
    a: float,
    b: float,
    status: Status,
    provisional: bool = False,
    at: datetime = NOW,
    pack: LanguagePack = PACK,
) -> ProfileEntry:
    """A profile entry holding the given decayed evidence, estimated as `build_profile` does."""
    definition = TAX.get(key)
    state = BetaState(a, b, at)
    est = estimate(state, prior=pack.prior_for(key), level=DEFAULT_CONFIG.interval_level)
    return ProfileEntry(
        definition=definition,
        state=state,
        estimate=est,
        status=status,
        last_seen_at=at,
        priority=est.p_hat * definition.impact,
        provisional=provisional,
    )


def profile_of(entries: Iterable[ProfileEntry], as_of: datetime = NOW) -> Profile:
    return Profile(
        as_of=as_of,
        taxonomy_version=TAX.version,
        algo_version=ALGO_VERSION,
        pack_id=PACK.id,
        entries=tuple(entries),
    )
