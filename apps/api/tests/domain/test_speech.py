from datetime import UTC, datetime

import pytest
from provider_fakes import raw_result

from nosolear.domain.analyses import AnalysisKind, StoredAnalysis
from nosolear.domain.coach import Rubric
from nosolear.domain.speech import (
    FREE_TALK_SCORING,
    PhoneProbeResult,
    ScoringMode,
    WordTiming,
    new_analysis,
    raw_result_of,
)


def stored_from(new, *, row_id: int = 1) -> StoredAnalysis:
    """What the analyses table returns for a NewAnalysis: the same fields plus id and created_at."""
    return StoredAnalysis(
        id=row_id,
        attempt_id=new.attempt_id,
        kind=new.kind,
        provider=new.provider,
        provider_version=new.provider_version,
        adapter=new.adapter,
        adapter_version=new.adapter_version,
        raw=new.raw,
        created_at=datetime(2026, 11, 13, 9, 0, tzinfo=UTC),
    )


@pytest.mark.parametrize("start,end", [(-1, 5), (10, 9)])
def test_word_timing_rejects_bad_spans(start, end):
    with pytest.raises(ValueError):
        WordTiming("vest", start, end)


def test_rubric_range():
    Rubric(0, 4, 2)
    with pytest.raises(ValueError):
        Rubric(5, 0, 0)


def test_phone_probe_expected_is_flat():
    r = PhoneProbeResult(
        expected_words=(("s", "k", "u", "l"), ("ɪ", "z")), heard=("s",), raw=raw_result()
    )
    assert r.expected == ("s", "k", "u", "l", "ɪ", "z")


def test_free_talk_default_is_unscripted_until_live_comparison():
    assert FREE_TALK_SCORING is ScoringMode.UNSCRIPTED


def test_raw_result_round_trips_through_an_analysis_row():
    raw = raw_result(adapter="azure_pa", payload={"mode": "scripted"})
    stored = stored_from(new_analysis("a1", AnalysisKind.PRONUNCIATION, raw))
    assert raw_result_of(stored) == raw
