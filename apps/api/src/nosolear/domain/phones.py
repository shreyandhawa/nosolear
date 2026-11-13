"""Phone symbols: espeak-ng and wav2vec2 output normalized to Azure's en-US IPA set. Pure.

Azure's pronunciation scores use this phone set, so both sides of a comparison are mapped here
first. `_MAP` grows only when a spike shows a symbol, with a test and a reason. A symbol with no
defensible Azure equivalent raises `UnmappedSymbol`: the rule is to fail loudly, never to guess.
"""

from collections.abc import Iterable

AZURE_CONSONANTS: frozenset[str] = frozenset(
    {
        "b",
        "d",
        "dʒ",
        "ð",
        "f",
        "ɡ",
        "h",
        "j",
        "k",
        "l",
        "m",
        "n",
        "ŋ",
        "p",
        "ɹ",
        "s",
        "ʃ",
        "t",
        "tʃ",
        "θ",
        "v",
        "w",
        "z",
        "ʒ",
    }
)
AZURE_VOWELS: frozenset[str] = frozenset(
    {
        "i",
        "ɪ",
        "eɪ",
        "ɛ",
        "æ",
        "ɑ",
        "ɔ",
        "oʊ",
        "ʊ",
        "u",
        "ʌ",
        "ə",
        "ɚ",
        "ɝ",
        "aɪ",
        "aʊ",
        "ɔɪ",
    }
)
AZURE_PHONES: frozenset[str] = AZURE_CONSONANTS | AZURE_VOWELS

_MAP: dict[str, str] = {
    "r": "ɹ",  # ASCII r is espeak's name for the English r, which Azure writes ɹ
    "g": "ɡ",  # ASCII g to IPA script g
    "d͡ʒ": "dʒ",  # tie-bar affricate to the single Azure phone
    "t͡ʃ": "tʃ",
    "ɜː": "ɝ",  # long r-coloured vowel (NURSE)
    "ɜ": "ɝ",
    "iː": "i",  # length mark dropped: Azure has no long vowels
    "uː": "u",
    "ɑː": "ɑ",
    "ɔː": "ɔ",
    "ɔːɹ": "ɔ ɹ",  # espeak's r-coloured compounds are two Azure phones
    "ɑːɹ": "ɑ ɹ",
    "ɪɹ": "ɪ ɹ",
    "iə": "ɪ",  # espeak's NEAR diphthong before a separate ɹ (for example "zero")
}
_UNSTRESSED = {ord(mark): None for mark in "ˈˌ"}  # primary and secondary stress


class UnmappedSymbol(ValueError):
    def __init__(self, symbol: str) -> None:
        super().__init__(f"unmapped phone symbol: {symbol!r}")
        self.symbol = symbol


def normalize(symbol: str) -> str:
    """One Azure phone for `symbol`; an espeak compound comes back space-separated (use
    `normalize_all` for a flat list)."""
    if symbol in AZURE_PHONES:
        return symbol
    if symbol in _MAP:
        return _MAP[symbol]
    unstressed = symbol.translate(_UNSTRESSED)
    if unstressed != symbol:
        return normalize(unstressed)
    if symbol.endswith("ː") and symbol[:-1] in AZURE_PHONES:  # a bare length mark is dropped
        return symbol[:-1]
    raise UnmappedSymbol(symbol)


def normalize_all(symbols: Iterable[str]) -> list[str]:
    return [phone for symbol in symbols for phone in normalize(symbol).split()]


def split_espeak_ipa(output: str) -> list[list[str]]:
    """espeak-ng `--ipa --sep=_` output: words on whitespace, phones on `_`. Empty pieces are
    dropped. Symbols are not normalized yet."""
    words: list[list[str]] = []
    for word in output.split():
        phones = [piece for piece in word.split("_") if piece]
        if phones:
            words.append(phones)
    return words
