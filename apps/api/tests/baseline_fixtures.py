"""A small baseline protocol for the tests: two read-aloud sentences, one word-list item, one
free-talk prompt, one rapid question and one articulate prompt. Import as
`from baseline_fixtures import small_baseline_content, PROTOCOL`.
"""

from calibration_fixtures import SMALL_SET

from nosolear.domain.attempts import AttemptStep
from nosolear.domain.content import (
    BaselineItem,
    BaselineProtocol,
    BaselineSection,
    ContentItem,
    ContentKind,
    SeedContent,
)


def _item(
    item_id: str,
    kind: ContentKind,
    text: str,
    tokens: dict[str, tuple[str, ...]] | None = None,
    stand_in: str | None = None,
) -> BaselineItem:
    annotated = tokens or {}
    return BaselineItem(
        item=ContentItem(item_id, kind, text, tuple(annotated)),
        stand_in=stand_in,
        tokens=annotated,
    )


PROTOCOL = BaselineProtocol(
    version=1,
    sections=(
        BaselineSection(
            name="read_aloud",
            step=AttemptStep.READ_ALOUD,
            items=(
                _item(
                    "bl:read:1",
                    ContentKind.PASSAGE_SENTENCE,
                    "Seven vans came.",
                    {"sound.sub.v.w": ("vans",)},
                ),
                _item(
                    "bl:read:2",
                    ContentKind.PASSAGE_SENTENCE,
                    "Five fine fans.",
                    {"sound.sub.f.p": ("fine",)},
                ),
            ),
            max_seconds=None,
            start_limit_seconds=None,
        ),
        BaselineSection(
            name="word_list",
            step=AttemptStep.WORD_LIST,
            items=(_item("bl:word:1", ContentKind.MINIMAL_PAIR, "vest"),),
            max_seconds=None,
            start_limit_seconds=None,
        ),
        BaselineSection(
            name="free_talk",
            step=AttemptStep.SPEAK,
            items=(
                _item(
                    "bl:free:1",
                    ContentKind.PROMPT,
                    "Tell me about your day.",
                    stand_in="Tell me about your day.",
                ),
            ),
            max_seconds=90,
            start_limit_seconds=None,
        ),
        BaselineSection(
            name="rapid_questions",
            step=AttemptStep.QUICK_ANSWER,
            items=(
                _item(
                    "bl:rapid:1",
                    ContentKind.QUICK_QUESTION,
                    "What is your name?",
                    stand_in="What is your name?",
                ),
            ),
            max_seconds=None,
            start_limit_seconds=5,
        ),
        BaselineSection(
            name="articulate",
            step=AttemptStep.ARTICULATE,
            items=(
                _item(
                    "bl:art:1",
                    ContentKind.PROMPT,
                    "Describe your home.",
                    stand_in="Describe your home.",
                ),
            ),
            max_seconds=60,
            start_limit_seconds=None,
        ),
    ),
    stress_pairs=(),
)


def small_baseline_content() -> SeedContent:
    return SeedContent(SMALL_SET, PROTOCOL)
