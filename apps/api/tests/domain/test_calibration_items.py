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


# The shipped table, typed out independently of items.toml so a typo there fails.
EXPECTED_SPECS = (
    ("sound.sub.v.w", "W instead of V", (("vest", "west"), ("very", "werry"), ("van", "wan"))),
    ("sound.sub.w.v", "V instead of W", (("west", "vest"), ("wine", "vine"))),
    ("sound.sub.f.p", "P instead of F", (("fan", "pan"), ("fine", "pine"), ("coffee", "coppee"))),
    (
        "sound.sub.θ.t",
        "T instead of TH",
        (("think", "tink"), ("three", "tree"), ("thanks", "tanks")),
    ),
    ("sound.sub.ð.d", "D instead of the voiced TH", (("this", "dis"), ("they", "day"))),
    ("sound.sub.ʃ.s", "S instead of SH", (("ship", "sip"), ("she", "see"), ("shop", "sop"))),
    ("sound.sub.s.ʃ", "SH instead of S", (("sip", "ship"), ("see", "she"))),
    ("sound.sub.z.dʒ", "a J sound instead of Z", (("zoo", "joo"), ("zero", "jero"))),
    ("sound.sub.z.s", "S instead of Z", (("zip", "sip"), ("buzz", "buss"))),
    (
        "sound.ins.epenthesis_sC",
        "a vowel before it",
        (("school", "ischool"), ("speak", "ispeak"), ("street", "istreet"), ("sport", "isport")),
    ),
)


def _expected_pairs() -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for key, description, words in EXPECTED_SPECS:
        for word, respelling in words:
            tail = f'"{respelling}"' if key.endswith("sC") else f'sounds like "{respelling}"'
            pairs.append(
                (f"{word}__correct", f'Say "{word}" as correctly as possible, in General American.')
            )
            for take in (1, 2):
                pairs.append(
                    (
                        f"{word}__err{take}",
                        f'Say "{word}" with {description}: {tail} (take {take} of 2)',
                    )
                )
    return pairs


def test_shipped_specs_match_the_pinned_table():
    assert tuple((s.error_key, s.description, s.words) for s in SPECS) == EXPECTED_SPECS


def test_shipped_items_match_the_pinned_78_id_instruction_pairs():
    pairs = [(i.id, i.instruction) for i in build_calibration_items(SPECS)]
    assert len(pairs) == 78
    assert pairs == _expected_pairs()
