"""Keeps configured secrets out of every log record, whichever logger or handler emits it."""

import logging
import traceback
from collections.abc import Callable, Iterable

from nosolear.domain.redaction import scrub

_original_factory: Callable[..., logging.LogRecord] | None = None
_secrets: tuple[str, ...] = ()


def _scrubbed_message(record: logging.LogRecord) -> str:
    try:
        message = record.getMessage()
    except TypeError, ValueError, KeyError:  # mismatched format arguments
        message = f"{record.msg} {record.args}"
    return scrub(message, _secrets)


def _factory(*args: object, **kwargs: object) -> logging.LogRecord:
    assert _original_factory is not None
    record = _original_factory(*args, **kwargs)
    record.msg = _scrubbed_message(record)
    record.args = None
    if record.exc_info and record.exc_info[1] is not None:
        formatted = "".join(traceback.format_exception(*record.exc_info)).rstrip("\n")
        record.exc_text = scrub(formatted, _secrets)
    if record.stack_info:
        record.stack_info = scrub(record.stack_info, _secrets)
    return record


def install_secret_scrubbing(secrets: Iterable[str]) -> None:
    """Scrub `secrets` from all later log records. Calling again replaces the earlier secrets."""
    global _original_factory, _secrets
    _secrets = tuple(secrets)
    if _original_factory is None:
        _original_factory = logging.getLogRecordFactory()
        logging.setLogRecordFactory(_factory)


def uninstall_secret_scrubbing() -> None:
    global _original_factory, _secrets
    if _original_factory is not None:
        logging.setLogRecordFactory(_original_factory)
    _original_factory = None
    _secrets = ()
