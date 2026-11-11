import math
from datetime import UTC, datetime, timedelta, timezone
from typing import Any

import pytest

from nosolear.domain.observations import Context, DetectorNotAllowed, Outcome, make_observation
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as T
from nosolear.domain.taxonomy import Detector

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
