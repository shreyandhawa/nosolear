import pytest

from nosolear.adapters.content_files import load_calibration_specs
from nosolear.domain.calibration_items import (
    CalibrationSpec,
    build_calibration_items,
    parse_calibration_specs,
    validate_calibration_specs,
)
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.settings import CONTENT_DIR

SPECS = load_calibration_specs(CONTENT_DIR / "calibration" / "items.toml")


def test_shipped_specs_build_78_unique_items():
    items = build_calibration_items(SPECS)
    assert len(items) == 78
    assert len({i.id for i in items}) == 78


def test_ten_specs_and_26_words():
    assert len(SPECS) == 10
    assert sum(len(s.words) for s in SPECS) == 26


def test_ids_flags_and_instructions_for_vest():
    spec = CalibrationSpec("sound.sub.v.w", "W instead of V", (("vest", "west"),))
    items = build_calibration_items([spec])
    assert [i.id for i in items] == ["vest__correct", "vest__err1", "vest__err2"]
    assert [i.deliberate for i in items] == [False, True, True]
    assert items[0].instruction == 'Say "vest" as correctly as possible, in General American.'
    assert (
        items[1].instruction == 'Say "vest" with W instead of V: sounds like "west" (take 1 of 2)'
    )
    assert items[2].instruction.endswith("(take 2 of 2)")
    assert {i.error_key for i in items} == {"sound.sub.v.w"}


def test_epenthesis_instruction():
    spec = next(s for s in SPECS if s.error_key == "sound.ins.epenthesis_sC")
    items = {i.id: i for i in build_calibration_items([spec])}
    assert (
        items["school__err1"].instruction
        == 'Say "school" with a vowel before it: "ischool" (take 1 of 2)'
    )


def test_every_spec_key_is_in_the_taxonomy():
    assert validate_calibration_specs(SPECS, DEFAULT_TAXONOMY) == ()


def test_unknown_key_yields_a_problem():
    bad = CalibrationSpec("grammar.artcle", "d", (("a", "b"),))
    assert validate_calibration_specs([bad], DEFAULT_TAXONOMY)


def test_duplicate_words_yield_a_problem():
    spec = CalibrationSpec("sound.sub.v.w", "d", (("vest", "west"),))
    assert validate_calibration_specs([spec, spec], DEFAULT_TAXONOMY)


def test_parse_rejects_malformed():
    with pytest.raises(ValueError):
        parse_calibration_specs(
            {"specs": [{"error_key": "x", "description": "d", "words": [["a"]]}]}
        )
    with pytest.raises(ValueError):
        parse_calibration_specs({})
