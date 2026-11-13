"""Keeps configured secrets out of log records, whichever logger or handler emits them.

Covered: the message, its arguments, the traceback (chained too; `exc_info` is cleared once the
scrubbed `exc_text` is cached) and `stack_info`. Not covered: `extra=` fields (set after the
factory runs).
"""

import logging
import traceback
from collections.abc import Callable, Iterable, Mapping
from typing import cast

from nosolear.domain.redaction import scrub_forms, secret_forms

UNFORMATTABLE = "<unformattable log message>"
_UNFORMATTABLE_TRACEBACK = "<unformattable traceback>"

_original_factory: Callable[..., logging.LogRecord] | None = None
_forms: tuple[str, ...] = ()


def _scrub(text: str) -> str:
    return scrub_forms(text, _forms)


def _scrub_arg(arg: object) -> object:
    if isinstance(arg, str):
        return _scrub(arg)
    try:
        shown = str(arg)
    except Exception:
        return UNFORMATTABLE
    scrubbed = _scrub(shown)
    return scrubbed if scrubbed != shown else arg


def _scrub_args(args: object) -> object:
    if isinstance(args, tuple):
        return tuple(_scrub_arg(a) for a in cast("tuple[object, ...]", args))
    if isinstance(args, Mapping):
        return {k: _scrub_arg(v) for k, v in cast("Mapping[object, object]", args).items()}
    return args


def _full_message(record: logging.LogRecord) -> str:
    """The scrubbed message, formatted from the record as it is now; never raises."""
    try:
        return _scrub(record.getMessage())
    except Exception:
        try:
            return _scrub(f"{record.msg} {record.args}")
        except Exception:
            return UNFORMATTABLE


def _scrub_message(record: logging.LogRecord) -> None:
    """Scrub template and arguments in place so formatters that read `args` still work."""
    original_msg, original_args = record.msg, record.args
    try:
        if isinstance(record.msg, str):
            record.msg = _scrub(record.msg)
        record.args = _scrub_args(record.args)  # pyright: ignore[reportAttributeAccessIssue]
        formatted = record.getMessage()
        if _scrub(formatted) == formatted:
            return
    except Exception:
        pass
    record.msg, record.args = original_msg, original_args
    record.msg = _full_message(record)
    record.args = None


def _factory(*args: object, **kwargs: object) -> logging.LogRecord:
    assert _original_factory is not None
    record = _original_factory(*args, **kwargs)
    try:
        _scrub_message(record)
    except Exception:
        record.msg, record.args = UNFORMATTABLE, None
    if record.exc_info and record.exc_info[1] is not None:
        try:
            formatted = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
            record.exc_text = _scrub(formatted)
        except Exception:
            record.exc_text = _UNFORMATTABLE_TRACEBACK
        # the stdlib Formatter still appends the cached `exc_text`; dropping `exc_info` stops
        # formatters that render it themselves (JSON, structlog, Rich) re-rendering the raw one
        record.exc_info = None
    if record.stack_info:
        record.stack_info = _scrub(record.stack_info)
    return record


def install_secret_scrubbing(secrets: Iterable[str]) -> None:
    """Scrub `secrets` from all later log records. Calling again replaces the earlier secrets."""
    global _original_factory, _forms
    _forms = secret_forms(secrets)
    current = logging.getLogRecordFactory()
    if current is not _factory:  # first install, or another library replaced our factory
        _original_factory = current
        logging.setLogRecordFactory(_factory)


def uninstall_secret_scrubbing() -> None:
    global _original_factory, _forms
    if _original_factory is not None and logging.getLogRecordFactory() is _factory:
        logging.setLogRecordFactory(_original_factory)
    _original_factory = None
    _forms = ()


QUIET_LOGGERS = ("httpx", "httpcore", "httpx2", "httpcore2", "anthropic", "azure")
"""Client libraries whose INFO and DEBUG records can carry request details; kept at WARNING."""


def quiet_third_party_loggers() -> None:
    for name in QUIET_LOGGERS:
        logging.getLogger(name).setLevel(logging.WARNING)
