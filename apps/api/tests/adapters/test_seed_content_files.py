"""The committed seed content: every pack's calibration set and the baseline protocol."""

import pytest

from nosolear.adapters.content_files import (
    list_pack_ids,
    load_baseline_protocol,
    load_calibration_set,
    load_pack,
    load_seed_content,
)
from nosolear.domain.calibration_items import EPENTHESIS_KEY
from nosolear.domain.content import (
    ContentInvalid,
    validate_baseline_protocol,
    validate_calibration_set,
)
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY as TAX
from nosolear.domain.taxonomy import Family
from nosolear.settings import CONTENT_DIR

PACKS_DIR = CONTENT_DIR / "packs"
NEUTRAL = load_pack(PACKS_DIR, "neutral")
NEPALI = load_pack(PACKS_DIR, "nepali")
SALVAGED_26 = {
    "vest", "very", "van", "west", "wine", "fan", "fine", "coffee", "think", "three", "thanks",
    "this", "they", "ship", "she", "shop", "sip", "see", "zoo", "zero", "zip", "buzz", "school",
    "speak", "street", "sport",
}  # fmt: skip


@pytest.mark.parametrize("pack_id", list_pack_ids(PACKS_DIR))
def test_every_pack_calibration_set_meets_the_minimum(pack_id: str):
    cs = load_calibration_set(CONTENT_DIR, load_pack(PACKS_DIR, pack_id))
    validate_calibration_set(cs, TAX)
    keys = cs.keys()
    for key in keys:
        assert len(cs.words_for(key)) >= 5
        assert len(cs.words_for(key)) * cs.takes_per_word >= 5


def test_salvaged_words_are_kept():
    words = {w.word for w in load_calibration_set(CONTENT_DIR, NEUTRAL).words}
    assert words >= SALVAGED_26


def test_nepali_emphasis_keys_are_calibratable():
    cs = load_calibration_set(CONTENT_DIR, NEPALI)
    keys = cs.keys()
    for key in NEPALI.calibration_emphasis:
        if TAX.get(key).family in (Family.SUB, Family.INS, Family.DEL):
            assert key in keys


def test_committed_baseline_protocol_is_valid():
    validate_baseline_protocol(load_baseline_protocol(CONTENT_DIR), TAX)


def test_committed_seed_content_loads_for_every_pack():
    for pack_id in list_pack_ids(PACKS_DIR):
        content = load_seed_content(CONTENT_DIR, load_pack(PACKS_DIR, pack_id))
        assert len(content.calibration_set.words) >= 50


def test_protocol_word_list_and_rapid_questions_match_the_brief():
    protocol = load_baseline_protocol(CONTENT_DIR)
    names = [s.name for s in protocol.sections]
    assert names == ["read_aloud", "word_list", "free_talk", "rapid_questions", "articulate"]
    word_list = protocol.sections[1]
    assert [i.item.text for i in word_list.items] == [
        "vest west vine wine fan",
        "pan sip ship sea she",
        "think thin this then zest",
        "jest zoo school speak street",
    ]
    rapid = protocol.sections[3]
    assert len(rapid.items) == 5 and rapid.start_limit_seconds == 5


def test_missing_protocol_file_is_content_invalid(tmp_path):
    with pytest.raises(ContentInvalid):
        load_baseline_protocol(tmp_path)


def test_malformed_protocol_json_is_content_invalid(tmp_path):
    (tmp_path / "baseline").mkdir()
    (tmp_path / "baseline" / "protocol.json").write_text("{not json", encoding="utf-8")
    with pytest.raises(ContentInvalid) as err:
        load_baseline_protocol(tmp_path)
    assert "\n" not in str(err.value)


def test_epenthesis_has_a_calibration_set_and_protocol_coverage():
    assert EPENTHESIS_KEY in load_calibration_set(CONTENT_DIR, NEUTRAL).keys()  # noqa: SIM118
