"""The analysis steps of an ANALYZE job (ARCHITECTURE.md section 13, Phase 0d).

Each step looks up its own stored analysis first and returns without a provider call when one
exists; otherwise it calls one port and stores the raw result for its attempt. A step never
passes anything from the model or the provider into a path, a command or a query.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from nosolear.app.steps import StepContext
from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.attempts import AttemptStep
from nosolear.domain.coach import coach_keys, coach_task_for_step
from nosolear.domain.errors import RequestNotSent
from nosolear.domain.results import parse_transcript
from nosolear.domain.scoring import enabled_keys
from nosolear.domain.speech import (
    FREE_TALK_SCORING as DEFAULT_FREE_TALK_SCORING,
)
from nosolear.domain.speech import (
    ScoringMode,
    new_analysis,
    raw_result_of,
)
from nosolear.domain.taxonomy import Detector, Taxonomy
from nosolear.ports.analyses import AnalysisStore
from nosolear.ports.audio import AttemptInfo, AttemptReader, AudioStore, RecordingStore
from nosolear.ports.providers import Coach, PhoneProbe, PronunciationScorer, Transcriber
from nosolear.ports.scoring_stores import ScoringConfigReader

FREE_TALK_SCORING: ScoringMode = DEFAULT_FREE_TALK_SCORING
"""How unscripted speech is scored (ARCHITECTURE.md section 4). Read at run time, so a test can
set it; the default is the domain's setting."""


@dataclass(frozen=True, slots=True)
class _Stores:
    analyses: AnalysisStore
    recordings: RecordingStore
    attempts: AttemptReader
    audio: AudioStore

    def attempt(self, ctx: StepContext) -> AttemptInfo | None:
        return self.attempts.get(_attempt_id(ctx))

    def wav(self, attempt_id: str) -> Path:
        recording = self.recordings.for_attempt(attempt_id)
        if recording is None:
            raise ValueError("The attempt has no recording.")
        return self.audio.resolve(recording.path)


def _attempt_id(ctx: StepContext) -> str:
    if ctx.attempt_id is None:
        raise ValueError("An analysis job needs an attempt.")
    return ctx.attempt_id


class ScoreStep:
    name = "score"

    def __init__(self, *, scorer: PronunciationScorer, stores: _Stores) -> None:
        self._scorer = scorer
        self._stores = stores

    def applies(self, ctx: StepContext) -> bool:
        return True

    def run(self, ctx: StepContext) -> None:
        attempt_id = _attempt_id(ctx)
        if self._stores.analyses.get(attempt_id, AnalysisKind.PRONUNCIATION) is not None:
            return
        info = self._stores.attempts.get(attempt_id)
        if info is None:
            raise ValueError("No attempt has this id.")
        reference = info.reference_text if info.scripted else self._free_talk_reference(attempt_id)
        result = self._scorer.score(self._stores.wav(attempt_id), reference_text=reference)
        self._stores.analyses.put(new_analysis(attempt_id, AnalysisKind.PRONUNCIATION, result.raw))

    def _free_talk_reference(self, attempt_id: str) -> str | None:
        """Unscripted speech is scored against its own transcript only when the setting says so;
        the plan runs transcribe before score for that to take effect."""
        if FREE_TALK_SCORING is not ScoringMode.CONTINUOUS:
            return None
        stored = self._stores.analyses.get(attempt_id, AnalysisKind.TRANSCRIPT)
        if stored is None:
            return None
        return parse_transcript(raw_result_of(stored)).text


class TranscribeStep:
    name = "transcribe"

    def __init__(self, *, transcriber: Transcriber, stores: _Stores) -> None:
        self._transcriber = transcriber
        self._stores = stores

    def applies(self, ctx: StepContext) -> bool:
        info = self._stores.attempt(ctx)
        return info is None or info.step != AttemptStep.CALIBRATION.value

    def run(self, ctx: StepContext) -> None:
        attempt_id = _attempt_id(ctx)
        if self._stores.analyses.get(attempt_id, AnalysisKind.TRANSCRIPT) is not None:
            return
        result = self._transcriber.transcribe(self._stores.wav(attempt_id))
        self._stores.analyses.put(new_analysis(attempt_id, AnalysisKind.TRANSCRIPT, result.raw))


class ProbeStep:
    name = "probe"

    def __init__(
        self,
        *,
        probe: PhoneProbe | None,
        stores: _Stores,
        configs: ScoringConfigReader,
        taxonomy: Taxonomy,
        tracked: Callable[[], frozenset[str]],
    ) -> None:
        self._probe = probe
        self._stores = stores
        self._configs = configs
        self._taxonomy = taxonomy
        self._tracked = tracked

    def applies(self, ctx: StepContext) -> bool:
        """Under `v0` the phone probe scores nothing, so it runs only for calibration and drill
        attempts, or when the newest config enables a phone-probe key."""
        if self._probe is None:
            return False
        info = self._stores.attempt(ctx)
        if info is None or not info.scripted or info.reference_text is None:
            return False
        if info.step in (AttemptStep.CALIBRATION.value, AttemptStep.DRILL.value):
            return True
        enabled = enabled_keys(
            self._configs.newest(), Detector.PHONE_PROBE, self._tracked(), self._taxonomy
        )
        return bool(enabled)

    def run(self, ctx: StepContext) -> None:
        attempt_id = _attempt_id(ctx)
        if self._probe is None:
            raise ValueError("The phone probe is not installed.")
        if self._stores.analyses.get(attempt_id, AnalysisKind.PHONE_PROBE) is not None:
            return
        info = self._stores.attempts.get(attempt_id)
        if info is None or info.reference_text is None:
            raise ValueError("The probe needs a scripted reference.")
        result = self._probe.probe(self._stores.wav(attempt_id), reference_text=info.reference_text)
        self._stores.analyses.put(new_analysis(attempt_id, AnalysisKind.PHONE_PROBE, result.raw))


class CoachStep:
    name = "coach"

    def __init__(self, *, coach: Coach, taxonomy: Taxonomy, stores: _Stores) -> None:
        self._coach = coach
        self._taxonomy = taxonomy
        self._stores = stores

    def applies(self, ctx: StepContext) -> bool:
        info = self._stores.attempt(ctx)
        return info is not None and coach_task_for_step(info.step) is not None

    def run(self, ctx: StepContext) -> None:
        attempt_id = _attempt_id(ctx)
        if self._stores.analyses.get(attempt_id, AnalysisKind.COACH) is not None:
            return
        info = self._stores.attempts.get(attempt_id)
        task = coach_task_for_step(info.step) if info is not None else None
        if info is None or task is None:
            raise ValueError("This attempt gets no coach call.")
        stored = self._stores.analyses.get(attempt_id, AnalysisKind.TRANSCRIPT)
        if stored is None:
            raise RequestNotSent("There is no transcript to coach.")
        text = parse_transcript(raw_result_of(stored)).text
        analysis = self._coach.analyze(
            task=task,
            prompt_text=info.reference_text or "",
            transcript=text,
            allowed_keys=coach_keys(self._taxonomy, task),
        )
        self._stores.analyses.put(new_analysis(attempt_id, AnalysisKind.COACH, analysis.raw))


def provider_steps(
    *,
    scorer: PronunciationScorer,
    transcriber: Transcriber,
    phone_probe: PhoneProbe | None,
    coach: Coach,
    taxonomy: Taxonomy,
    analyses: AnalysisStore,
    recordings: RecordingStore,
    attempts: AttemptReader,
    audio: AudioStore,
    configs: ScoringConfigReader,
    tracked: Callable[[], frozenset[str]],
) -> tuple[ScoreStep | TranscribeStep | ProbeStep | CoachStep, ...]:
    stores = _Stores(analyses=analyses, recordings=recordings, attempts=attempts, audio=audio)
    return (
        ScoreStep(scorer=scorer, stores=stores),
        TranscribeStep(transcriber=transcriber, stores=stores),
        ProbeStep(
            probe=phone_probe,
            stores=stores,
            configs=configs,
            taxonomy=taxonomy,
            tracked=tracked,
        ),
        CoachStep(coach=coach, taxonomy=taxonomy, stores=stores),
    )
