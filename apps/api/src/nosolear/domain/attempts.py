"""Session kinds and attempt steps. Their values are the schema's CHECK lists."""

from enum import StrEnum


class SessionKind(StrEnum):
    BASELINE = "baseline"
    DAILY = "daily"
    RETEST = "retest"
    CONVERSATION = "conversation"
    CALIBRATION = "calibration"


class AttemptStep(StrEnum):
    SPEAK = "speak"
    READ_ALOUD = "read_aloud"
    WORD_LIST = "word_list"
    QUICK_ANSWER = "quick_answer"
    ARTICULATE = "articulate"
    RETELL = "retell"
    DRILL = "drill"
    SHADOW = "shadow"
    CALIBRATION = "calibration"
