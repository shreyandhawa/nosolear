import pytest

from nosolear.domain.phones import (
    AZURE_PHONES,
    UnmappedSymbol,
    normalize,
    normalize_all,
    split_espeak_ipa,
)

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


@pytest.mark.parametrize("sym", ["ɾ", "ᵻ", "ɐ", "ʔ"])
def test_symbols_without_a_defensible_azure_equivalent_stay_unmapped(sym):
    # Flap, reduced vowel, near-open central vowel, glottal stop: no Azure phone is the same
    # sound, so mapping one would be a guess. They are listed in HANDOFF for the owner.
    with pytest.raises(UnmappedSymbol) as info:
        normalize(sym)
    assert info.value.symbol == sym


def test_every_symbol_swept_from_espeak_normalizes():
    assert normalize_all(SWEPT_PIECES)


def test_split_espeak_ipa():
    assert split_espeak_ipa("s_k_ˈuː_l ð_ə\n") == [["s", "k", "ˈuː", "l"], ["ð", "ə"]]


def test_split_espeak_ipa_drops_empty_pieces():
    assert split_espeak_ipa("  s__k_  \n\n") == [["s", "k"]]
    assert split_espeak_ipa("") == []
