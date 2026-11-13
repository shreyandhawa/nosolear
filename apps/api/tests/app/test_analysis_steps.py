import uuid
from datetime import UTC, datetime
from pathlib import Path

import pytest
from factories import FixedClock
from fakes import (
    FakeAnalysisStore,
    FakeAttemptReader,
    FakeAudioStore,
    FakeJobQueue,
    FakeRecordingStore,
)
from provider_fakes import (
    FakeCoach,
    FakePhoneProbe,
    FakeScorer,
    FakeTranscriber,
    assessment,
    raw_result,
)

import nosolear.app.analysis_steps as analysis_steps
from nosolear.app.analysis_steps import provider_steps
from nosolear.app.steps import StepContext
from nosolear.domain.analyses import AnalysisKind
from nosolear.domain.coach import CoachAnalysis, CoachTask, coach_keys
from nosolear.domain.errors import RequestNotSent
from nosolear.domain.jobs import JobKind
from nosolear.domain.speech import FREE_TALK_SCORING, PhoneProbeResult, ScoringMode, Transcript
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.ports.audio import AttemptInfo, NewRecording, StoredRecording

NOW = datetime(2026, 11, 13, 9, 0, tzinfo=UTC)
FREE_KEYS = coach_keys(TAX, CoachTask.FREE_TALK)


class World:
    """Fakes for every port the analysis steps read, with one recording per attempt."""

    def __init__(self, tmp_path: Path, attempts: list[AttemptInfo]) -> None:
        clock = FixedClock(NOW)
        self.analyses = FakeAnalysisStore(clock)
        self.attempts = FakeAttemptReader(attempts)
        self.jobs = FakeJobQueue(clock)
        self.recordings = FakeRecordingStore(self.jobs)
        self.audio = FakeAudioStore()
        for info in attempts:
            stored = StoredRecording(
                path=f"recordings/{uuid.uuid4()}.wav",
                duration_ms=2000,
                sample_rate=16000,
                sha256="0" * 64,
            )
            self.recordings.add_and_enqueue(NewRecording(attempt_id=info.id, stored=stored))

    def steps(self, *, scorer, transcriber, phone_probe=None, coach=None):
        return {
            step.name: step
            for step in provider_steps(
                scorer=scorer,
                transcriber=transcriber,
                phone_probe=phone_probe,
                coach=coach or FakeCoach(),
                taxonomy=TAX,
                analyses=self.analyses,
                recordings=self.recordings,
                attempts=self.attempts,
                audio=self.audio,
            )
        }


def ctx(attempt_id: str) -> StepContext:
    return StepContext(
        job_id="job-1", kind=JobKind.ANALYZE, attempt_id=attempt_id, progress=lambda _f: None
    )


def attempt(step: str, *, scripted: bool, reference: str | None) -> AttemptInfo:
    return AttemptInfo(
        id=uuid.uuid4().hex,
        session_id=uuid.uuid4().hex,
        step=step,
        reference_text=reference,
        scripted=scripted,
    )


def spoken(text: str) -> Transcript:
    """A transcript whose stored payload the real parser reads back to `text`."""
    payload: dict[str, object] = {
        "results": [{"RecognitionStatus": "Success", "DisplayText": text}]
    }
    return Transcript(
        text=text,
        words=(),
        fillers_kept=False,
        raw=raw_result(adapter="azure_stt", provider="azure", payload=payload),
    )


def probe_result() -> PhoneProbeResult:
    raw = raw_result(adapter="wav2vec2_espeak", provider="local")
    return PhoneProbeResult(expected_words=(("v",),), heard=("v",), raw=raw)


def coach_result() -> CoachAnalysis:
    return CoachAnalysis(
        findings=(),
        rubric=None,
        rewrite=None,
        dropped=0,
        tokens_used=10,
        raw=raw_result(adapter="claude_coach", provider="anthropic"),
    )


def stored_kinds(world: World, attempt_id: str) -> set[AnalysisKind]:
    return {row.kind for row in world.analyses.for_attempt(attempt_id)}


def test_a_scripted_drill_scores_with_its_reference_and_probes(tmp_path):
    info = attempt("drill", scripted=True, reference="The vest is west.")
    world = World(tmp_path, [info])
    scorer = FakeScorer(results=[assessment()])
    probe = FakePhoneProbe(results=[probe_result()])
    steps = world.steps(scorer=scorer, transcriber=FakeTranscriber(), phone_probe=probe)

    for name in ("score", "probe"):
        assert steps[name].applies(ctx(info.id))
        steps[name].run(ctx(info.id))

    assert scorer.calls[0][1] == "The vest is west."
    assert probe.calls[0][1] == "The vest is west."
    assert stored_kinds(world, info.id) == {AnalysisKind.PRONUNCIATION, AnalysisKind.PHONE_PROBE}
    assert not steps["coach"].applies(ctx(info.id))  # a drill gets no coach call


def test_an_unscripted_speak_scores_with_no_reference_and_coaches_free_talk(tmp_path):
    info = attempt("speak", scripted=False, reference=None)
    world = World(tmp_path, [info])
    scorer = FakeScorer(results=[assessment()])
    transcriber = FakeTranscriber(results=[spoken("I go to the market")])
    coach = FakeCoach(results=[coach_result()])
    probe = FakePhoneProbe(results=[probe_result()])
    steps = world.steps(scorer=scorer, transcriber=transcriber, phone_probe=probe, coach=coach)

    steps["score"].run(ctx(info.id))
    steps["transcribe"].run(ctx(info.id))
    assert steps["coach"].applies(ctx(info.id))
    steps["coach"].run(ctx(info.id))

    assert scorer.calls[0][1] is None
    assert not steps["probe"].applies(ctx(info.id))  # the probe needs a scripted reference
    task, _prompt, text, keys = coach.calls[0]
    assert task is CoachTask.FREE_TALK
    assert text == "I go to the market"
    assert keys == FREE_KEYS
    assert stored_kinds(world, info.id) == {
        AnalysisKind.PRONUNCIATION,
        AnalysisKind.TRANSCRIPT,
        AnalysisKind.COACH,
    }


def test_probe_does_not_apply_without_a_phone_probe(tmp_path):
    info = attempt("drill", scripted=True, reference="The vest is west.")
    world = World(tmp_path, [info])
    steps = world.steps(scorer=FakeScorer(), transcriber=FakeTranscriber(), phone_probe=None)
    assert not steps["probe"].applies(ctx(info.id))


def test_a_stored_analysis_is_returned_without_a_port_call(tmp_path):
    info = attempt("drill", scripted=True, reference="The vest is west.")
    world = World(tmp_path, [info])
    scorer = FakeScorer(results=[assessment()])
    steps = world.steps(scorer=scorer, transcriber=FakeTranscriber())
    steps["score"].run(ctx(info.id))
    steps["score"].run(ctx(info.id))
    assert len(scorer.calls) == 1


def test_the_transcript_is_stored_and_reused_for_coaching(tmp_path):
    info = attempt("quick_answer", scripted=False, reference=None)
    world = World(tmp_path, [info])
    transcriber = FakeTranscriber(results=[spoken("Yesterday I go")])
    steps = world.steps(
        scorer=FakeScorer(), transcriber=transcriber, coach=FakeCoach([coach_result()])
    )
    steps["transcribe"].run(ctx(info.id))
    steps["transcribe"].run(ctx(info.id))
    assert len(transcriber.calls) == 1
    steps["coach"].run(ctx(info.id))
    assert stored_kinds(world, info.id) == {AnalysisKind.TRANSCRIPT, AnalysisKind.COACH}


def test_coach_without_a_stored_transcript_sends_no_request(tmp_path):
    info = attempt("speak", scripted=False, reference=None)
    world = World(tmp_path, [info])
    coach = FakeCoach([coach_result()])
    steps = world.steps(scorer=FakeScorer(), transcriber=FakeTranscriber(), coach=coach)
    with pytest.raises(RequestNotSent):
        steps["coach"].run(ctx(info.id))
    assert coach.calls == []


def test_under_continuous_free_talk_the_stored_transcript_is_the_reference(tmp_path, monkeypatch):
    monkeypatch.setattr(analysis_steps, "FREE_TALK_SCORING", ScoringMode.CONTINUOUS)
    info = attempt("speak", scripted=False, reference=None)
    world = World(tmp_path, [info])
    scorer = FakeScorer(results=[assessment()])
    steps = world.steps(
        scorer=scorer, transcriber=FakeTranscriber(results=[spoken("I go to the market")])
    )
    steps["transcribe"].run(ctx(info.id))
    steps["score"].run(ctx(info.id))
    assert scorer.calls[0][1] == "I go to the market"


def test_the_default_free_talk_scoring_is_unscripted():
    assert FREE_TALK_SCORING is ScoringMode.UNSCRIPTED
    assert analysis_steps.FREE_TALK_SCORING is ScoringMode.UNSCRIPTED


def test_steps_are_named_as_the_plan_names_them(tmp_path):
    world = World(tmp_path, [])
    steps = world.steps(scorer=FakeScorer(), transcriber=FakeTranscriber())
    assert set(steps) == {"score", "transcribe", "probe", "coach"}
