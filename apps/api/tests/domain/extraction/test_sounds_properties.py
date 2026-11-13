"""Properties of sound extraction over generated Azure and probe results."""

import copy

from factories import PACK, TAX
from hypothesis import given
from strategies import probe_results, pronunciation_results

from nosolear.domain.extraction.opportunities import tracked_keys
from nosolear.domain.extraction.sounds import azure_opportunities, probe_opportunities
from nosolear.domain.scoring import V0_THRESHOLDS, Thresholds
from nosolear.domain.speech import PhonemeAssessment, PhoneProbeResult, PronunciationAssessment

ALL = tracked_keys(TAX, PACK)
SKIPPED = ("Omission", "Insertion")


def v0(_: str) -> Thresholds:
    return V0_THRESHOLDS


def _scored_phones(r: PronunciationAssessment) -> list[PhonemeAssessment]:
    return [p for w in r.words if w.error_type not in SKIPPED for p in w.phonemes]


@given(r=pronunciation_results(has_nbest=True))
def test_sub_opportunities_equal_expected_phone_count(r: PronunciationAssessment) -> None:
    opps = azure_opportunities(r, keys=ALL, thresholds_for=v0)
    phones = _scored_phones(r)
    for key in (k for k in ALL if k.startswith("sound.sub.")):
        expected = key.rsplit(".", 2)[1]
        assert sum(o.error_key == key for o in opps) == sum(p.phoneme == expected for p in phones)


@given(r=pronunciation_results())
def test_a_phoneme_yields_at_most_one_substitution_miss(r: PronunciationAssessment) -> None:
    opps = azure_opportunities(r, keys=ALL, thresholds_for=v0)
    phones = _scored_phones(r)
    for e in {p.phoneme for p in phones}:
        misses = sum(o.missed for o in opps if o.error_key.startswith(f"sound.sub.{e}."))
        assert misses <= sum(p.phoneme == e for p in phones)


@given(r=pronunciation_results(), p=probe_results())
def test_sound_extraction_is_deterministic(r: PronunciationAssessment, p: PhoneProbeResult) -> None:
    assert azure_opportunities(r, keys=ALL, thresholds_for=v0) == azure_opportunities(
        copy.deepcopy(r), keys=ALL, thresholds_for=v0
    )
    assert probe_opportunities(p, reference_text=None, keys=ALL) == probe_opportunities(
        copy.deepcopy(p), reference_text=None, keys=ALL
    )
