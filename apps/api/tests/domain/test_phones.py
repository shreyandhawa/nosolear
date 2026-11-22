import pytest

from nosolear.adapters.content_files import list_pack_ids, load_pack, load_seed_content
from nosolear.adapters.local_env import espeak_ng_path
from nosolear.adapters.wav2vec2_espeak import espeak_ipa
from nosolear.domain.phones import (
    AZURE_PHONES,
    UNKNOWN,
    UnmappedSymbol,
    normalize,
    normalize_all,
    normalize_heard,
    split_espeak_ipa,
)
from nosolear.settings import CONTENT_DIR

# Symbols espeak-ng printed for the calibration words (content/calibration/items.toml) and a
# draft probe sentence, swept on 2026-11-13 with `espeak-ng -q -v en-us --ipa --sep=_ --stdin`.
SWEPT_PIECES = [
    "s",
    "k",
    "p",
    "ˈɪ",
    "t",
    "ɹ",
    "n",
    "ˈiː",
    "z",
    "ˈæ",
    "v",
    "i",
    "ˈɑː",
    "ˈaɪ",
    "ŋ",
    "θ",
    "ð",
    "ˈɛ",
    "w",
    "f",
    "iː",
    "l",
    "ˈuː",
    "ʃ",
    "b",
    "ˈʌ",
    "d",
    "dʒ",
    "ˈiə",
    "oʊ",
    "ˈeɪ",
    "ə",
    "ˈɔ",
    "uː",
    "ɔːɹ",
    "ˈɔːɹ",
    "eɪ",
    "ɪ",
    "ˈaʊ",
    "m",
    "ˌoʊ",
    "ɚ",
    "ɡ",
]


def test_azure_phones_map_to_themselves():
    assert all(normalize(p) == p for p in AZURE_PHONES)


@pytest.mark.parametrize(
    ("sym", "out"),
    [
        ("r", "ɹ"),
        ("g", "ɡ"),
        ("d͡ʒ", "dʒ"),
        ("t͡ʃ", "tʃ"),
        ("ɜː", "ɝ"),
        ("iː", "i"),
        ("ˈæ", "æ"),
        ("ˌɪ", "ɪ"),
        ("ʊː", "ʊ"),
        ("iə", "ɪ"),
    ],
)
def test_salvaged_map(sym, out):
    assert normalize(sym) == out


def test_compounds_split():
    assert normalize_all(["ɔːɹ", "ɪɹ"]) == ["ɔ", "ɹ", "ɪ", "ɹ"]


def test_unknown_symbol_fails_loudly():
    with pytest.raises(UnmappedSymbol) as info:
        normalize("q")
    assert info.value.symbol == "q" and isinstance(info.value, ValueError)


@pytest.mark.parametrize(
    ("sym", "out"),
    [
        ("ɛɹ", ["ɛ", "ɹ"]),
        ("ɐ", ["ə"]),
        ("ˈᵻ", ["ɪ"]),
        ("əl", ["ə", "l"]),
        ("aɪə", ["aɪ", "ə"]),
        ("n̩", ["ə", "n"]),
        ("ɾ", ["t"]),
        ("ʔ", ["t"]),
    ],
)
def test_espeak_gaps_found_by_the_coverage_sweep(sym, out):
    assert normalize_all([sym]) == out


def test_heard_side_turns_an_unmapped_symbol_into_unknown():
    assert normalize_all(["q", "s"], heard=True) == [UNKNOWN, "s"]
    assert normalize_heard("ɐ") == "ə"


def test_every_shipped_content_text_maps_through_espeak():
    exe = espeak_ng_path()
    if exe is None:
        pytest.skip("espeak-ng is not installed")
    packs = CONTENT_DIR / "packs"
    texts: set[str] = set()
    for pack_id in list_pack_ids(packs):
        seed = load_seed_content(CONTENT_DIR, load_pack(packs, pack_id))
        texts |= {w.word for w in seed.calibration_set.words}
        texts |= {i.item.text for s in seed.protocol.sections for i in s.items}
    unmapped = set()
    for text in sorted(texts):
        ipa = espeak_ipa(text, executable=exe)
        for word in split_espeak_ipa(ipa):
            for symbol in word:
                try:
                    normalize(symbol)
                except UnmappedSymbol:
                    unmapped.add(symbol)
    assert not unmapped


def test_every_symbol_swept_from_espeak_normalizes():
    assert normalize_all(SWEPT_PIECES)


def test_split_espeak_ipa():
    assert split_espeak_ipa("s_k_ˈuː_l ð_ə\n") == [["s", "k", "ˈuː", "l"], ["ð", "ə"]]


def test_split_espeak_ipa_drops_empty_pieces():
    assert split_espeak_ipa("  s__k_  \n\n") == [["s", "k"]]
    assert split_espeak_ipa("") == []
