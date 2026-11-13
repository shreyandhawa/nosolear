from collections.abc import Sequence
from datetime import timedelta

from factories import DAY, PACK, T0, TAX, mk

from nosolear.domain.baseline_report import (
    BaselineReport,
    CalibrationState,
    ClipRef,
    build_baseline_report,
)
from nosolear.domain.observations import Observation, Outcome
from nosolear.domain.profile import Profile, build_profile
from nosolear.domain.skill_scores import SkillScore
from nosolear.domain.taxonomy import Skill

MISS, OK = Outcome.MISS, Outcome.OK
VW = "sound.sub.v.w"
FP = "sound.sub.f.p"
LOW_T = "sound.low.t"


def _report(
    session: list[Observation],
    *,
    history: Sequence[Observation] = (),
    calibration: CalibrationState = CalibrationState.CALIBRATED,
    fillers_undercounted: bool = False,
    coach_scored: bool = True,
    max_clips: int = 3,
    skills: tuple[SkillScore, ...] = (),
) -> BaselineReport:
    everything = [*history, *session]
    profile: Profile = build_profile(everything, as_of=T0, taxonomy=TAX, pack=PACK)
    return build_baseline_report(
        session_id="s1",
        completed_at=T0,
        profile=profile,
        session_observations=session,
        skill_scores=skills,
        calibration=calibration,
        scoring_config_id="v0",
        snapshot_id="snap1",
        fillers_undercounted=fillers_undercounted,
        coach_scored=coach_scored,
        max_clips=max_clips,
    )


def _miss(key: str, at_ms: int, *, attempt: str = "a1", **evidence: object) -> Observation:
    data: dict[str, object] = {"start_ms": at_ms, "end_ms": at_ms + 400, **evidence}
    return mk(key, MISS, T0 + timedelta(seconds=at_ms // 1000), evidence=data, attempt_id=attempt)


def test_items_are_keys_missed_this_session_ranked_by_priority():
    history = [mk(LOW_T, MISS, T0 - DAY * 3)] * 4
    session = [
        _miss(VW, 100),
        _miss(VW, 200),
        _miss(FP, 300),
        mk(FP, OK, T0),
    ]
    r = _report(session, history=history)
    keys = [item.error_key for item in r.items]
    assert keys == [VW, FP]
    assert r.items[0].priority >= r.items[1].priority
    assert LOW_T not in keys


def test_clips_point_at_the_users_misses():
    session = [
        _miss(VW, 900, word="vest", expected="v", produced="w", attempt="a9"),
        _miss(VW, 100, word="vest", expected="v", produced="w", attempt="a1"),
        _miss(VW, 500, word="vine", expected="v", produced="w", attempt="a2"),
        _miss(VW, 700, word="vet", expected="v", produced="w", attempt="a3"),
        mk(VW, OK, T0, evidence={"start_ms": 50, "end_ms": 90}, attempt_id="a4"),
        _miss(FP, 50, word="fine", expected="f", produced="p", attempt="a5"),
    ]
    item = next(i for i in _report(session).items if i.error_key == VW)
    assert item.clips == (
        ClipRef("a1", 100, 500, "vest", "v", "w"),
        ClipRef("a2", 500, 900, "vine", "v", "w"),
        ClipRef("a3", 700, 1100, "vet", "v", "w"),
    )


def test_clips_are_capped_at_max_clips():
    session = [_miss(VW, 100 * i, attempt=f"a{i}") for i in range(1, 6)]
    item = next(i for i in _report(session, max_clips=2).items if i.error_key == VW)
    assert len(item.clips) == 2


def test_clip_fields_are_none_when_evidence_lacks_them():
    session = [_miss(VW, 100, attempt="a1")]
    clip = next(i for i in _report(session).items if i.error_key == VW).clips[0]
    assert (clip.word, clip.expected, clip.produced) == (None, None, None)


def test_provisional_flag_comes_from_the_profile_entry():
    session = [
        mk(VW, MISS, T0, provisional=True, attempt_id="a1"),
        mk(FP, MISS, T0, provisional=False, attempt_id="a2"),
    ]
    flags = {i.error_key: i.provisional for i in _report(session).items}
    assert flags == {VW: True, FP: False}


def test_notes_when_calibration_was_skipped_and_fillers_and_coach_are_missing():
    r = _report(
        [_miss(VW, 100)],
        calibration=CalibrationState.SKIPPED,
        fillers_undercounted=True,
        coach_scored=False,
    )
    assert r.notes == (
        "Calibration was skipped: sound and prosody scores are provisional.",
        "Fillers may be undercounted: this transcriber drops filler words.",
        "The coach was unavailable: grammar, structure and clarity were not scored.",
    )


def test_notes_when_calibration_was_never_run():
    r = _report([_miss(VW, 100)], calibration=CalibrationState.NOT_RUN)
    assert r.notes == ("Calibration hasn't been run: sound and prosody scores are provisional.",)


def test_no_notes_when_everything_is_in_place():
    r = _report([_miss(VW, 100)])
    assert r.notes == ()


def test_skill_scores_and_ids_are_carried_through():
    skill = SkillScore(Skill.ARTICULATE, 75.0, {"rubric": 3.0}, {"rubric": 75.0})
    r = _report([_miss(VW, 100)], skills=(skill,))
    assert r.skill_scores == (skill,)
    assert (r.session_id, r.scoring_config_id, r.snapshot_id) == ("s1", "v0", "snap1")
    assert r.calibration is CalibrationState.CALIBRATED
