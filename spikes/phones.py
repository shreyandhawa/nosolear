"""Normalize espeak / wav2vec2 phone symbols to Azure en-US IPA. Fails loudly on unknown symbols.

Extend _MAP whenever a spike shows a new mismatch; never guess.
normalize() returns one Azure phone, except for espeak compounds that are really two phones
(`ɪɹ`, `ɔːɹ`, ...), which come back space-separated; use normalize_all() to get a flat list.
"""

AZURE_CONSONANTS = {"b", "d", "dʒ", "ð", "f", "ɡ", "h", "j", "k", "l", "m", "n", "ŋ", "p", "ɹ", "s", "ʃ",
                    "t", "tʃ", "θ", "v", "w", "z", "ʒ"}
AZURE_VOWELS = {"i", "ɪ", "eɪ", "ɛ", "æ", "ɑ", "ɔ", "oʊ", "ʊ", "u", "ʌ", "ə", "ɚ", "ɝ", "aɪ", "aʊ", "ɔɪ"}
AZURE_PHONES = AZURE_CONSONANTS | AZURE_VOWELS

# Symbols that need an explicit mapping (everything else must already be an Azure phone).
_MAP = {
    "r": "ɹ",
    "g": "ɡ",          # ASCII g -> IPA script g
    "d͡ʒ": "dʒ",       # tie-bar affricates
    "t͡ʃ": "tʃ",
    "ɜː": "ɝ",
    "ɜ": "ɝ",
    "iː": "i",
    "uː": "u",
    "ɑː": "ɑ",
    "ɔː": "ɔ",
    "ɔːɹ": "ɔ ɹ",      # espeak r-colored compounds are two Azure phones
    "ɑːɹ": "ɑ ɹ",
    "ɪɹ": "ɪ ɹ",
    "iə": "ɪ",         # espeak's NEAR diphthong before a separate ɹ (e.g. "zero")
}
_STRIP = "ːˈˌ"        # length mark, primary and secondary stress


class UnmappedSymbol(Exception):
    def __init__(self, symbol: str):
        super().__init__(f"unmapped phone symbol: {symbol!r}")
        self.symbol = symbol


def normalize(symbol: str) -> str:
    if symbol in AZURE_PHONES:
        return symbol
    if symbol in _MAP:
        return _MAP[symbol]
    stripped = symbol.translate({ord(c): None for c in "ˈˌ"})
    if stripped != symbol:
        return normalize(stripped)
    if symbol.endswith("ː") and symbol[:-1] in AZURE_PHONES:   # bare length mark dropped: iː -> i
        return symbol[:-1]
    raise UnmappedSymbol(symbol)


def normalize_all(symbols: list[str]) -> list[str]:
    return [p for s in symbols for p in normalize(s).split()]
