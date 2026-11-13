"""Seed content: calibration sets and the baseline protocol, built from synthetic content only."""

from dataclasses import replace

import pytest

from nosolear.domain.attempts import AttemptStep
from nosolear.domain.calibration_items import EPENTHESIS_KEY, CalibrationSpec
from nosolear.domain.content import (
    BASELINE_PROTOCOL_VERSION,
    BaselineItem,
    BaselineProtocol,
    BaselineSection,
    CalibrationSet,
    CalibrationWord,
    ContentInvalid,
    ContentItem,
    ContentKind,
    SeedContent,
    calibration_instruction,
    calibration_set,
    seed_items,
    stand_in_text,
    validate_baseline_protocol,
    validate_calibration_set,
)
from nosolear.domain.packs import CalibrationExtra
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Family

REQUIRED_KEYS = sorted(
    {d.key for d in TAX.defined() if d.family in (Family.SUB, Family.LOW)} | {EPENTHESIS_KEY}
)


def spec(key: str, description: str, *pairs: tuple[str, str]) -> CalibrationSpec:
    return CalibrationSpec(key, description, tuple(pairs))


def small_set(words_per_key: int = 5) -> CalibrationSet:
    specs = [
        spec(
            "sound.sub.v.w", "W instead of V", *[(f"v{i}", f"w{i}") for i in range(words_per_key)]
        ),
        spec(
            "sound.sub.f.p", "P instead of F", *[(f"f{i}", f"p{i}") for i in range(words_per_key)]
        ),
    ]
    return calibration_set(specs)


def item(
    item_id: str,
    kind: ContentKind,
    text: str,
    tokens: dict[str, tuple[str, ...]] | None = None,
    stand_in: str | None = None,
) -> BaselineItem:
    annotated = dict(tokens or {})
    content = ContentItem(item_id, kind, text, tuple(annotated), "seed")
    return BaselineItem(content, stand_in, annotated)


def synthetic_protocol() -> BaselineProtocol:
    """A valid protocol: one passage sentence per required key, with three annotated words each,
    padded with filler to the passage's word range."""
    sentences = [
        item(
            f"ba-ra-{n:02d}",
            ContentKind.PASSAGE_SENTENCE,
            f"Try word{n}a word{n}b word{n}c today.",
            {key: (f"word{n}a", f"word{n}b", f"word{n}c")},
        )
        for n, key in enumerate(REQUIRED_KEYS, start=1)
    ]
    filler = [
        item(f"ba-ra-{len(sentences) + 1:02d}", ContentKind.PASSAGE_SENTENCE, "We record it now."),
        item(
            f"ba-ra-{len(sentences) + 2:02d}",
            ContentKind.PASSAGE_SENTENCE,
            "Please record the record and then rest for a short while here.",
        ),
        item(
            f"ba-ra-{len(sentences) + 3:02d}",
            ContentKind.PASSAGE_SENTENCE,
            "Keep your voice relaxed and steady while you read each line slowly.",
        ),
    ]
    word_list = [
        item(
            f"ba-wl-{n:02d}",
            ContentKind.MINIMAL_PAIR,
            text,
        )
        for n, text in enumerate(
            [
                "vest west vine wine fan",
                "pan sip ship sea she",
                "think thin this then zest",
                "jest zoo school speak street",
            ],
            start=1,
        )
    ]
    rapid = [
        item(
            f"ba-rq-{n:02d}",
            ContentKind.QUICK_QUESTION,
            "What color is the sky on a clear day?",
            stand_in="It is blue.",
        )
        for n in range(1, 6)
    ]
    return BaselineProtocol(
        version=BASELINE_PROTOCOL_VERSION,
        sections=(
            BaselineSection(
                "read_aloud", AttemptStep.READ_ALOUD, tuple(sentences + filler), None, None
            ),
            BaselineSection("word_list", AttemptStep.WORD_LIST, tuple(word_list), None, None),
            BaselineSection(
                "free_talk",
                AttemptStep.SPEAK,
                (
                    item(
                        "ba-ft-01",
                        ContentKind.PROMPT,
                        "Describe a place you love.",
                        stand_in="A lake.",
                    ),
                ),
                90,
                None,
            ),
            BaselineSection("rapid_questions", AttemptStep.QUICK_ANSWER, tuple(rapid), 15, 5),
            BaselineSection(
                "articulate",
                AttemptStep.ARTICULATE,
                (
                    item(
                        "ba-ar-01",
                        ContentKind.PROMPT,
                        "Give one point and an example.",
                        stand_in="A point.",
                    ),
                ),
                60,
                None,
            ),
        ),
        stress_pairs=("record",),
    )


def test_synthetic_protocol_is_valid():
    validate_baseline_protocol(synthetic_protocol(), TAX)


def test_rejects_a_key_with_too_few_words():
    with pytest.raises(ContentInvalid):
        validate_calibration_set(small_set(4), TAX)


def test_accepts_a_key_with_five_words():
    validate_calibration_set(small_set(5), TAX)


def test_rejects_a_non_sound_calibration_key():
    bad = calibration_set(
        [
            spec(
                "grammar.article",
                "a or the",
                ("a", "b"),
                ("c", "d"),
                ("e", "f"),
                ("g", "h"),
                ("i", "j"),
            )
        ]
    )
    with pytest.raises(ContentInvalid):
        validate_calibration_set(bad, TAX)


def test_rejects_a_word_equal_to_its_respelling():
    bad = calibration_set(
        [
            spec(
                "sound.sub.v.w",
                "W instead of V",
                ("v", "w"),
                ("a", "a"),
                ("b", "c"),
                ("d", "e"),
                ("f", "g"),
            )
        ]
    )
    with pytest.raises(ContentInvalid):
        validate_calibration_set(bad, TAX)


def test_extras_are_appended_to_their_key_in_file_order():
    cs = calibration_set(
        [
            spec("sound.sub.v.w", "W instead of V", ("vest", "west")),
            spec("sound.sub.f.p", "P instead of F", ("fan", "pan")),
        ],
        extras=[CalibrationExtra("sound.sub.v.w", "van", "wan")],
    )
    assert cs.keys() == ("sound.sub.v.w", "sound.sub.f.p")
    assert [w.word for w in cs.words_for("sound.sub.v.w")] == ["vest", "van"]
    assert cs.word("cal:sound.sub.v.w:van") is not None


def test_an_extra_without_a_respelling_is_rejected():
    with pytest.raises(ContentInvalid):
        calibration_set(
            [spec("sound.sub.v.w", "W instead of V", ("vest", "west"))],
            extras=[CalibrationExtra("sound.sub.v.w", "van", None)],
        )


def test_rejects_thin_coverage_of_a_contrast():
    protocol = synthetic_protocol()
    first = protocol.sections[0]
    thinned = []
    for entry in first.items:
        if "sound.sub.v.w" in entry.tokens:
            tokens = {"sound.sub.v.w": entry.tokens["sound.sub.v.w"][:2]}
            entry = replace(
                entry, tokens=tokens, item=replace(entry.item, target_keys=("sound.sub.v.w",))
            )
        thinned.append(entry)
    broken = replace(
        protocol, sections=(replace(first, items=tuple(thinned)), *protocol.sections[1:])
    )
    with pytest.raises(ContentInvalid):
        validate_baseline_protocol(broken, TAX)


def test_rejects_a_token_missing_from_its_sentence():
    protocol = synthetic_protocol()
    first = protocol.sections[0]
    bad_first = replace(first.items[0], tokens={REQUIRED_KEYS[0]: ("nowhere", "word1b", "word1c")})
    broken = replace(
        protocol,
        sections=(replace(first, items=(bad_first, *first.items[1:])), *protocol.sections[1:]),
    )
    with pytest.raises(ContentInvalid):
        validate_baseline_protocol(broken, TAX)


def test_rejects_sections_out_of_order():
    protocol = synthetic_protocol()
    broken = replace(protocol, sections=tuple(reversed(protocol.sections)))
    with pytest.raises(ContentInvalid):
        validate_baseline_protocol(broken, TAX)


def test_rapid_questions_need_the_five_second_start_limit():
    protocol = synthetic_protocol()
    sections = list(protocol.sections)
    sections[3] = replace(sections[3], start_limit_seconds=6)
    with pytest.raises(ContentInvalid):
        validate_baseline_protocol(replace(protocol, sections=tuple(sections)), TAX)


def test_unscripted_items_need_a_stand_in():
    protocol = synthetic_protocol()
    sections = list(protocol.sections)
    free = sections[2]
    sections[2] = replace(free, items=(replace(free.items[0], stand_in=None),))
    with pytest.raises(ContentInvalid):
        validate_baseline_protocol(replace(protocol, sections=tuple(sections)), TAX)


def test_instruction_copy():
    w = CalibrationWord("cal:sound.sub.v.w:vest", "sound.sub.v.w", "vest", "west", "W instead of V")
    assert calibration_instruction(w, deliberate=True, take=1, takes=2) == (
        'Say "vest" with W instead of V: sounds like "west" (take 1 of 2)'
    )
    assert calibration_instruction(w, deliberate=False, take=1, takes=2) == (
        'Say "vest" as correctly as possible, in General American.'
    )
    assert stand_in_text(w, deliberate=True) == "west"
    assert stand_in_text(w, deliberate=False) == "vest"


def test_insertion_copy_has_no_sounds_like():
    w = CalibrationWord("cal:x:school", EPENTHESIS_KEY, "school", "ischool", "a vowel before it")
    assert calibration_instruction(w, deliberate=True, take=2, takes=2) == (
        'Say "school" with a vowel before it: "ischool" (take 2 of 2)'
    )


def test_seed_items_hold_every_calibration_word_and_protocol_item():
    cs = calibration_set([spec("sound.sub.v.w", "W instead of V", ("vest", "west"))])
    content = SeedContent(cs, synthetic_protocol())
    ids = [i.id for i in seed_items(content)]
    assert "cal:sound.sub.v.w:vest" in ids
    assert "ba-ft-01" in ids
    assert len(ids) == len(set(ids))
