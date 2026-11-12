import io
import logging
from collections.abc import Iterator
from urllib.parse import quote

import pytest

from nosolear.logging_setup import install_secret_scrubbing, uninstall_secret_scrubbing

KEY = "sk-test-0123456789abcdef"
OTHER = "other-key-fedcba9876543210"


@pytest.fixture(autouse=True)
def _clean() -> Iterator[None]:
    yield
    uninstall_secret_scrubbing()


def _logger(name: str) -> tuple[logging.Logger, io.StringIO]:
    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log = logging.getLogger(name)
    log.handlers = [handler]
    log.setLevel(logging.DEBUG)
    log.propagate = False
    return log, stream


def test_scrubs_message_and_args() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.args")
    log.info("key %s", KEY)
    log.info(f"key {KEY}")
    text = out.getvalue()
    assert KEY not in text
    assert text.count("[redacted]") == 2


def test_scrubs_traceback() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.tb")
    try:
        raise ValueError(f"bad {KEY}")
    except ValueError:
        log.exception("failed")
    assert KEY not in out.getvalue()
    assert "ValueError" in out.getvalue()


def test_scrubs_chained_traceback() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.chain")
    try:
        try:
            raise ValueError(KEY)
        except ValueError as inner:
            raise RuntimeError("outer") from inner
    except RuntimeError:
        log.exception("failed")
    assert KEY not in out.getvalue()
    assert "RuntimeError" in out.getvalue()


def test_scrubs_encoded_forms() -> None:
    key = "a b/c+d&e=f-0123456789"
    install_secret_scrubbing([key])
    log, out = _logger("t.enc")
    log.info("GET https://x/?k=%s", quote(key, safe=""))
    assert quote(key, safe="") not in out.getvalue()
    assert "[redacted]" in out.getvalue()


def test_scrubs_loggers_created_after_install() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("late")
    log.warning("k=%s", KEY)
    assert KEY not in out.getvalue()


def test_second_install_replaces_secrets() -> None:
    install_secret_scrubbing([KEY])
    install_secret_scrubbing([OTHER])
    log, out = _logger("t.second")
    log.info("%s %s", KEY, OTHER)
    assert OTHER not in out.getvalue()
    assert KEY in out.getvalue()


def test_mismatched_format_args_do_not_crash() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.bad")
    log.info("%s %s", KEY)
    assert KEY not in out.getvalue()
    assert out.getvalue()


def test_uninstall_restores_factory() -> None:
    original = logging.getLogRecordFactory()
    install_secret_scrubbing([KEY])
    assert logging.getLogRecordFactory() is not original
    uninstall_secret_scrubbing()
    assert logging.getLogRecordFactory() is original
