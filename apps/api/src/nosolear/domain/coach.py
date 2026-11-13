"""Coach result types. Types only: prompts and parsing arrive with the coach adapter.

Coach output is untrusted: these types carry what the model said after validation, never a
path, a command or a query. `error_key` values come from the taxonomy enum the request asked for.
"""

from dataclasses import dataclass
from enum import StrEnum

from nosolear.domain.speech import RawResult


class CoachTask(StrEnum):
    FREE_TALK = "free_talk"
    QUICK_ANSWERS = "quick_answers"
    ARTICULATE = "articulate"
    RETELL = "retell"


@dataclass(frozen=True, slots=True)
class CoachFinding:
    """A grammar finding always has a quote from the transcript; structure and clarity may not."""

    error_key: str
    quote: str | None
    correction: str
    explanation: str


@dataclass(frozen=True, slots=True)
class Rubric:
    structure: int
    clarity: int
    concision: int

    def __post_init__(self) -> None:
        for name, value in (
            ("structure", self.structure),
            ("clarity", self.clarity),
            ("concision", self.concision),
        ):
            if not 0 <= value <= 4:
                raise ValueError(f"rubric {name} must be between 0 and 4")


@dataclass(frozen=True, slots=True)
class CoachAnalysis:
    findings: tuple[CoachFinding, ...]
    rubric: Rubric | None
    rewrite: str | None
    dropped: int
    tokens_used: int
    raw: RawResult


@dataclass(frozen=True, slots=True)
class CoachExplanation:
    message: str
    model_text: str
    tokens_used: int
    raw: RawResult
