import pytest

from nosolear.adapters.content_files import list_pack_ids, load_calibration_specs, load_pack
from nosolear.domain.estimates import Prior
from nosolear.settings import CONTENT_DIR

PACKS_DIR = CONTENT_DIR / "packs"

PHASE_0A_HYPOTHESIS_KEYS = {  # keys whose taxonomy flag `hypothesis` was True in Phase 0a
    "sound.sub.v.w", "sound.sub.w.v", "sound.sub.f.p", "sound.sub.ʃ.s", "sound.sub.s.ʃ",
    "sound.sub.θ.t", "sound.sub.z.dʒ", "sound.sub.z.s", "sound.sub.ð.d", "sound.sub.ʒ.dʒ",
    "sound.sub.i.ɪ", "sound.sub.ɪ.i", "sound.sub.æ.ɛ", "sound.sub.ʌ.ɑ",
    "sound.low.t", "sound.low.d", "sound.low.ɹ", "sound.low.ɝ", "sound.low.θ", "sound.low.ð",
    "sound.ins.epenthesis_sC", "prosody.word_stress", "prosody.unexpected_break",
    "prosody.monotone",
    "grammar.article", "grammar.preposition",
}  # fmt: skip

SPIKE_EMPHASIS = (
    "sound.sub.v.w",
    "sound.sub.w.v",
    "sound.sub.f.p",
    "sound.sub.θ.t",
    "sound.sub.ð.d",
    "sound.sub.ʃ.s",
    "sound.sub.s.ʃ",
    "sound.sub.z.dʒ",
    "sound.sub.z.s",
    "sound.ins.epenthesis_sC",
)


@pytest.mark.parametrize("pack_id", list_pack_ids(PACKS_DIR))
def test_every_shipped_pack_loads(pack_id: str):
    assert load_pack(PACKS_DIR, pack_id).id == pack_id


def test_shipped_pack_ids():
    assert {"neutral", "nepali"} <= set(list_pack_ids(PACKS_DIR))


def test_neutral_is_flat():
    pack = load_pack(PACKS_DIR, "neutral")
    assert pack.hypotheses == ()
    assert pack.default_prior == Prior(1, 9)
    assert pack.calibration_emphasis == ()


def test_nepali_emphasis_is_the_spike_keys_in_order_and_each_has_a_spec():
    pack = load_pack(PACKS_DIR, "nepali")
    assert pack.calibration_emphasis == SPIKE_EMPHASIS
    spec_keys = {
        s.error_key for s in load_calibration_specs(CONTENT_DIR / "calibration" / "items.toml")
    }
    assert set(SPIKE_EMPHASIS) <= spec_keys


def test_nepali_hypotheses_are_exactly_the_phase_0a_flags():
    pack = load_pack(PACKS_DIR, "nepali")
    assert {h.key for h in pack.hypotheses} == PHASE_0A_HYPOTHESIS_KEYS
    assert len(pack.hypotheses) == len(PHASE_0A_HYPOTHESIS_KEYS)
    assert all(h.prior == Prior(1, 3) and h.reason for h in pack.hypotheses)
