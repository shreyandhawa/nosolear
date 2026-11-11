import math
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from nosolear.domain.estimates import BetaState, apply
from nosolear.domain.observations import Context, DetectorNotAllowed, Outcome, make_observation
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as T
from nosolear.domain.taxonomy import Detector, UnknownErrorKey

NPT = timezone(timedelta(hours=5, minutes=45))
T0 = datetime(2026, 11, 12, 8, 0, tzinfo=UTC)


def obs(**kw):
    base: dict[str, Any] = dict(
        taxonomy=T,
        error_key="sound.sub.v.w",
        outcome=Outcome.MISS,
        detector=Detector.AZURE_PA,
        context=Context.SCRIPTED,
        observed_at=T0,
    )
    return make_observation(**(base | kw))


def test_weights():
    assert obs().weight == 1.0
    assert obs(context=Context.UNSCRIPTED, confidence=0.8).weight == pytest.approx(0.4)


def test_rejects_naive_datetime():
    with pytest.raises(ValueError):
        obs(observed_at=datetime(2026, 11, 12, 8, 0))


def test_converts_offset_to_utc():
    o = obs(observed_at=datetime(2026, 11, 12, 13, 45, tzinfo=NPT))
    assert o.observed_at == T0 and o.observed_at.tzinfo == UTC


@pytest.mark.parametrize("c", [0.0, -0.1, 1.2, math.nan, math.inf])
def test_rejects_bad_confidence(c):
    with pytest.raises(ValueError):
        obs(confidence=c)


def test_rejects_detector_not_allowed():
    with pytest.raises(DetectorNotAllowed):
        obs(error_key="sound.ins.epenthesis_sC", detector=Detector.AZURE_PA)
    with pytest.raises(DetectorNotAllowed):
        obs(error_key="prosody.word_stress", detector=Detector.AZURE_PA)


def test_records_taxonomy_version_and_copies_evidence():
    ev = {"word": "vest"}
    o = obs(evidence=ev)
    ev["word"] = "changed"
    assert o.evidence == {"word": "vest"} and o.taxonomy_version == 1


def test_unknown_error_key_is_rejected():
    with pytest.raises(UnknownErrorKey):
        obs(error_key="sound.nope")


def test_plain_strings_are_coerced_to_enum_members():
    o = obs(outcome="miss", detector="azure_pa", context="unscripted")
    assert o.outcome is Outcome.MISS
    assert o.detector is Detector.AZURE_PA
    assert o.context is Context.UNSCRIPTED
    assert o.weight == 0.5


def test_plain_string_miss_counts_as_a_miss():
    state = BetaState(a=1.0, b=3.0, updated_at=T0)
    after = apply(state, obs(outcome="miss"))
    assert (after.a, after.b) == (2.0, 3.0)


@pytest.mark.parametrize(
    "field, value",
    [
        ("outcome", "bogus"),
        ("outcome", "MISS"),
        ("context", "bogus"),
        ("context", "Scripted"),
        ("detector", "bogus"),
        ("detector", "Azure_PA"),
    ],
)
def test_rejects_unknown_enum_values(field, value):
    with pytest.raises(ValueError):
        obs(**{field: value})


@pytest.mark.parametrize("c", [True, False, "0.5", None])
def test_rejects_non_numeric_or_bool_confidence(c):
    with pytest.raises(ValueError):
        obs(confidence=c)
