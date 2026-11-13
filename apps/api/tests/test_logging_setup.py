import io
import logging
import sys
from collections.abc import Iterator
from urllib.parse import quote

import pytest
from uvicorn.logging import AccessFormatter, DefaultFormatter

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
    assert "ValueError" in out.getvalue()
    assert "[redacted]" in out.getvalue()


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
    assert "[redacted]" in out.getvalue()


def test_uninstall_restores_factory() -> None:
    original = logging.getLogRecordFactory()
    install_secret_scrubbing([KEY])
    assert logging.getLogRecordFactory() is not original
    uninstall_secret_scrubbing()
    assert logging.getLogRecordFactory() is original


def test_scrubs_stack_info() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.stack")
    log.info("here", stack_info=True)  # sk-test-0123456789abcdef is in this source line
    text = out.getvalue()
    assert "test_scrubs_stack_info" in text
    assert "[redacted]" in text
    assert KEY not in text


class _Hostile:
    def __str__(self) -> str:
        raise RuntimeError("no str")

    def __repr__(self) -> str:
        raise RuntimeError("no repr")


def test_factory_never_raises() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.hostile")
    log.info("value %s", _Hostile())
    log.info("value %r and %s", _Hostile(), KEY)
    assert KEY not in out.getvalue()
    assert out.getvalue()


def _uvicorn_logger(name: str, formatter: logging.Formatter) -> tuple[logging.Logger, io.StringIO]:
    log, out = _logger(name)
    log.handlers[0].setFormatter(formatter)
    return log, out


_ACCESS = '%(levelprefix)s %(client_addr)s - "%(request_line)s" %(status_code)s'


def test_uvicorn_access_formatter_still_works(capsys: pytest.CaptureFixture[str]) -> None:
    install_secret_scrubbing([KEY])
    log, out = _uvicorn_logger("t.access", AccessFormatter(_ACCESS, use_colors=False))
    log.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5", "GET", "/api/health", "1.1", 200)
    assert 'GET /api/health HTTP/1.1" 200' in out.getvalue()
    assert "Logging error" not in capsys.readouterr().err


def test_uvicorn_access_formatter_scrubs_path(capsys: pytest.CaptureFixture[str]) -> None:
    install_secret_scrubbing([KEY])
    log, out = _uvicorn_logger("t.access2", AccessFormatter(_ACCESS, use_colors=False))
    log.info('%s - "%s %s HTTP/%s" %d', "127.0.0.1:5", "GET", f"/x?k={KEY}", "1.1", 200)
    assert KEY not in out.getvalue()
    assert "/x?k=[redacted]" in out.getvalue()
    assert "Logging error" not in capsys.readouterr().err


def test_uvicorn_default_formatter_scrubs() -> None:
    install_secret_scrubbing([KEY])
    log, out = _uvicorn_logger("t.default", DefaultFormatter("%(levelprefix)s %(message)s"))
    log.info("started with %s", KEY)
    assert KEY not in out.getvalue()
    assert "started with [redacted]" in out.getvalue()


def test_key_split_across_args_is_still_scrubbed() -> None:
    install_secret_scrubbing([KEY])
    log, out = _logger("t.split")
    log.info("%s%s", KEY[:10], KEY[10:])
    assert KEY not in out.getvalue()
    assert "[redacted]" in out.getvalue()


def test_reinstall_after_foreign_factory_replacement() -> None:
    install_secret_scrubbing([KEY])
    ours = logging.getLogRecordFactory()
    logging.setLogRecordFactory(logging.LogRecord)
    install_secret_scrubbing([KEY])
    assert logging.getLogRecordFactory() is ours
    log, out = _logger("t.rewrap")
    log.info("k=%s", KEY)
    assert KEY not in out.getvalue()


def test_exc_info_is_cleared_and_exc_text_is_scrubbed_and_cached() -> None:
    install_secret_scrubbing([KEY])
    try:
        raise RuntimeError(f"boom {KEY}")
    except RuntimeError:
        record = logging.getLogger("t.excinfo").makeRecord(
            "t.excinfo", logging.ERROR, __file__, 1, "failed", (), sys.exc_info()
        )
    assert record.exc_info is None
    assert record.exc_text is not None
    assert "Traceback" in record.exc_text and KEY not in record.exc_text
