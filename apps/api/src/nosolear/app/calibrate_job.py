"""The calibrate job's steps (ARCHITECTURE.md sections 9.2 and 13): `controls`, `evaluate` and
`queue_rescore`, in that order.

`controls` is the only step that spends quota. It synthesizes each distinct word once through the
composed `Synthesizer`, scores the clip with each detector the word's keys use, and stores the raw
result against the run, so a resumed job never pays for a clip twice. `evaluate` reads only stored
data, writes the flags, and completes the run with its calibrated config.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Final
from uuid import uuid4

from nosolear.app.steps import StepContext
from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.calibration import (
    build_calibrated_config,
    evaluate,
    flagged,
)
from nosolear.domain.jobs import JobKind
from nosolear.domain.results import parse_azure_pa, parse_phone_probe
from nosolear.domain.speech import RawResult, raw_result_of
from nosolear.domain.taxonomy import Detector
from nosolear.ports.analyses import AnalysisStore
from nosolear.ports.calibration_store import CalibrationStore
from nosolear.ports.clock import Clock
from nosolear.ports.jobs import JobQueue
from nosolear.ports.providers import PhoneProbe, PronunciationScorer, Synthesizer

KIND_OF: Final[Mapping[Detector, AnalysisKind]] = {
    Detector.AZURE_PA: AnalysisKind.PRONUNCIATION,
    Detector.PHONE_PROBE: AnalysisKind.PHONE_PROBE,
}


@dataclass(frozen=True, slots=True)
class _Word:
    text: str
    pairs: tuple[tuple[str, Detector], ...]


class ControlsStep:
    name = "controls"

    def __init__(
        self,
        *,
        store: CalibrationStore,
        synthesizer: Synthesizer,
        scorer: PronunciationScorer,
        phone_probe: PhoneProbe | None,
        data_dir: Path,
    ) -> None:
        self._store = store
        self._synthesizer = synthesizer
        self._scorer = scorer
        self._phone_probe = phone_probe
        self._data_dir = data_dir

    def applies(self, ctx: StepContext) -> bool:
        return True

    def run(self, ctx: StepContext) -> None:
        run = self._store.latest()
        if run is None or run.status != "running":
            return
        words = self._words(run.id)
        for index, word in enumerate(words):
            clip = self._synthesizer.synthesize(word.text)
            for detector in sorted({d for _, d in word.pairs}, key=lambda d: d.value):
                kind = KIND_OF[detector]
                if self._store.control_analysis(clip.hash, run.id, kind) is None:
                    raw = self._judge(detector, self._data_dir / clip.path, word.text)
                    self._store.add_control_analysis(clip.hash, run.id, kind, raw)
            self._store.add_control_trials(run.id, clip.hash, word.pairs)
            ctx.progress((index + 1) / len(words))

    def _words(self, run_id: str) -> list[_Word]:
        """Each distinct word of the run, with the (key, detector) pairs its trials use."""
        word_of = {item.attempt_id: item.word for item in self._store.items(run_id)}
        pairs: dict[str, list[tuple[str, Detector]]] = {}
        for record in self._store.trials(run_id):
            text = word_of.get(record.trial.attempt_id or "")
            if text is None:
                continue
            pair = (record.trial.error_key, record.trial.detector)
            bucket = pairs.setdefault(text, [])
            if pair not in bucket:
                bucket.append(pair)
        return [_Word(text, tuple(bucket)) for text, bucket in pairs.items()]

    def _judge(self, detector: Detector, wav: Path, word: str) -> RawResult:
        if detector is Detector.AZURE_PA:
            return self._scorer.score(wav, reference_text=word).raw
        if self._phone_probe is None:
            raise ValueError("The phone probe is not installed.")
        return self._phone_probe.probe(wav, reference_text=word).raw


class EvaluateStep:
    name = "evaluate"

    def __init__(
        self,
        *,
        store: CalibrationStore,
        analyses: AnalysisStore,
        capabilities: Callable[[], Mapping[str, object]],
        clock: Clock,
    ) -> None:
        self._store = store
        self._analyses = analyses
        self._capabilities = capabilities
        self._clock = clock

    def applies(self, ctx: StepContext) -> bool:
        return True

    def run(self, ctx: StepContext) -> None:
        run = self._store.latest()
        if run is None:
            raise ValueError("No calibration run has this id.")
        if run.status == "done":
            return
        if run.status != "running":
            raise ValueError("The calibration run is not open.")
        word_of = {item.attempt_id: item.word for item in self._store.items(run.id)}
        control_of = self._store.control_words(run.id)
        flags: dict[int, bool | None] = {}
        for record in self._store.trials(run.id):
            trial = record.trial
            kind = KIND_OF[trial.detector]
            if trial.attempt_id is not None:
                stored = self._analyses.get(trial.attempt_id, kind)
                raw = None if stored is None else raw_result_of(stored)
                text = word_of.get(trial.attempt_id)
            else:
                raw = self._store.control_analysis(trial.tts_hash or "", run.id, kind)
                text = control_of.get(trial.tts_hash or "")
            flags[record.id] = _flag(trial.detector, trial.error_key, raw, text)
        self._store.set_flags(flags)
        results = evaluate(record.trial for record in self._store.trials(run.id))
        config = build_calibrated_config(config_id=uuid4().hex, run_id=run.id, results=results)
        self._store.complete(
            run_id=run.id,
            config=config,
            capabilities=self._capabilities(),
            now=self._clock.now(),
        )


def _flag(
    detector: Detector, error_key: str, raw: RawResult | None, text: str | None
) -> bool | None:
    if raw is None or text is None:
        return None
    try:
        result = parse_azure_pa(raw) if detector is Detector.AZURE_PA else parse_phone_probe(raw)
        return flagged(detector, error_key, result, reference_text=text)
    except ValueError:
        return None


class QueueRescoreStep:
    name = "queue_rescore"

    def __init__(self, *, queue: JobQueue) -> None:
        self._queue = queue

    def applies(self, ctx: StepContext) -> bool:
        return True

    def run(self, ctx: StepContext) -> None:
        self._queue.enqueue(JobKind.RESCORE, None)
