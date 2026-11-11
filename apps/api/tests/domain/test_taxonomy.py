import pytest

from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as T
from nosolear.domain.taxonomy import Detector, Family, Skill, UnknownErrorKey

HYPOTHESES = [
    "sound.sub.v.w",
    "sound.sub.w.v",
    "sound.sub.f.p",
    "sound.sub.θ.t",
    "sound.sub.ð.d",
    "sound.sub.ʃ.s",
    "sound.sub.s.ʃ",
    "sound.sub.z.dʒ",
    "sound.ins.epenthesis_sC",
    "prosody.word_stress",
    "grammar.article",
]


def test_hypothesis_keys_present():
    assert all(T.get(k).hypothesis for k in HYPOTHESES)


def test_dynamic_substitution_key():
    d = T.get("sound.sub.p.b")
    assert (d.family, d.skill, d.impact, d.hypothesis) == (Family.SUB, Skill.SOUNDS, 1, False)
    assert d.detectors == frozenset({Detector.AZURE_PA, Detector.PHONE_PROBE})


@pytest.mark.parametrize(
    "bad",
    [
        "",
        "fluency",
        "grammar.artcle",
        "sound.sub.v",
        "sound.sub.v.v",
        "sound.sub..w",
        "sound.sub.v.w.x",
        "sound.low.",
        "sound.sub.v. w",
    ],
)
def test_rejects_malformed_keys(bad):
    with pytest.raises(UnknownErrorKey):
        T.get(bad)


def test_family_matches_skill_and_impact_range():
    sounds = {Family.SUB, Family.LOW, Family.INS, Family.DEL, Family.PROSODY}
    for d in T.defined():
        assert 1 <= d.impact <= 3
        assert (d.skill is Skill.SOUNDS) == (d.family in sounds)


def test_word_stress_not_scored_until_phase_2():
    assert T.get("prosody.word_stress").detectors == frozenset()


def test_dynamic_weak_sound_key():
    d = T.get("sound.low.k")
    assert (d.family, d.skill, d.impact, d.hypothesis) == (Family.LOW, Skill.SOUNDS, 1, False)
    assert d.drill_family == "sound_practice"
    assert d.detectors == frozenset({Detector.AZURE_PA})
    assert d.description == "/k/ unclear"


def test_descriptions_share_one_format_for_explicit_and_dynamic_keys():
    assert T.get("sound.sub.v.w").description == "/v/ said as /w/"
    assert T.get("sound.sub.p.b").description == "/p/ said as /b/"
    assert T.get("sound.low.t").description == "/t/ unclear"


def test_explicit_key_matches_table():
    d = T.get("grammar.verb_tense")
    assert (d.impact, d.drill_family, d.detectors, d.hypothesis) == (
        3,
        "grammar_rewrite",
        frozenset({Detector.COACH}),
        False,
    )
    assert T.get("sound.del.final_cluster").detectors == frozenset(
        {Detector.PHONE_PROBE, Detector.AZURE_PA}
    )


def test_defined_is_sorted_and_contains_matches_get():
    keys = [d.key for d in T.defined()]
    assert keys == sorted(keys)
    assert "sound.sub.v.w" in T and "sound.sub.p.b" in T
    assert "grammar.artcle" not in T and "" not in T


def test_every_defined_key_has_description():
    assert all(d.description.strip() for d in T.defined())
