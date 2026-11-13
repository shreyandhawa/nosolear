"""Phone alignment: the minimum-cost edit alignment of expected and heard phones (Needleman-Wunsch).

Costs: a match is free; a substitution costs 1.0 within a class (vowel or consonant) and 1.5
across classes; an insertion or deletion costs 1.0. Callers normalize with `domain/phones.py`
first, so a phone outside `AZURE_PHONES` is refused. Pure: no I/O.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Literal

from nosolear.domain.phones import AZURE_PHONES, AZURE_VOWELS

SUB_SAME_CLASS = 1.0
SUB_CROSS_CLASS = 1.5
INSERT = 1.0
DELETE = 1.0


@dataclass(frozen=True, slots=True)
class PhoneEdit:
    op: Literal["match", "sub", "ins", "del"]
    expected: str | None
    heard: str | None
    expected_index: int
    """For an insertion, the index of the expected phone it comes before (`len(expected)` at the
    end). For a match, a substitution or a deletion, the index of the expected phone."""


def _check(phones: Sequence[str]) -> None:
    for phone in phones:
        if phone not in AZURE_PHONES:
            raise ValueError(f"not an Azure phone: {phone!r}")


def _sub_cost(expected: str, heard: str) -> float:
    if expected == heard:
        return 0.0
    same_class = (expected in AZURE_VOWELS) == (heard in AZURE_VOWELS)
    return SUB_SAME_CLASS if same_class else SUB_CROSS_CLASS


def align_phones(expected: Sequence[str], heard: Sequence[str]) -> tuple[PhoneEdit, ...]:
    _check(expected)
    _check(heard)
    n, m = len(expected), len(heard)
    cost = [[0.0] * (m + 1) for _ in range(n + 1)]
    for i in range(1, n + 1):
        cost[i][0] = i * DELETE
    for j in range(1, m + 1):
        cost[0][j] = j * INSERT
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            cost[i][j] = min(
                cost[i - 1][j - 1] + _sub_cost(expected[i - 1], heard[j - 1]),
                cost[i - 1][j] + DELETE,
                cost[i][j - 1] + INSERT,
            )
    edits: list[PhoneEdit] = []
    i, j = n, m
    while i > 0 or j > 0:
        if i > 0 and j > 0:
            e, h = expected[i - 1], heard[j - 1]
            if cost[i][j] == cost[i - 1][j - 1] + _sub_cost(e, h):
                op: Literal["match", "sub"] = "match" if e == h else "sub"
                edits.append(PhoneEdit(op, e, h, i - 1))
                i, j = i - 1, j - 1
                continue
        if i > 0 and cost[i][j] == cost[i - 1][j] + DELETE:
            edits.append(PhoneEdit("del", expected[i - 1], None, i - 1))
            i -= 1
            continue
        edits.append(PhoneEdit("ins", None, heard[j - 1], i))
        j -= 1
    edits.reverse()
    return tuple(edits)
