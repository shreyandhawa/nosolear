"""Word error rate for the live transcription checks. Test-only: never imported by src."""

import re

_TOKEN = re.compile(r"[\w']+")


def _tokens(text: str) -> list[str]:
    return [token.casefold() for token in _TOKEN.findall(text)]


def word_error_rate(reference: str, hypothesis: str) -> float:
    """Word-level Levenshtein distance over case-folded word tokens, divided by the reference
    length. An empty reference scores 0 when the hypothesis is empty too, and 1 otherwise."""
    ref, hyp = _tokens(reference), _tokens(hypothesis)
    if not ref:
        return 0.0 if not hyp else 1.0
    previous = list(range(len(hyp) + 1))
    for i, word in enumerate(ref, start=1):
        current = [i]
        for j, other in enumerate(hyp, start=1):
            cost = 0 if word == other else 1
            current.append(min(previous[j] + 1, current[j - 1] + 1, previous[j - 1] + cost))
        previous = current
    return previous[-1] / len(ref)
