"""Planted fake keys and the registry of output surfaces that must never show them.

Later phases append `@leak_surface` producers (adapter error paths, job `steps_json`, ledger
rows, the coach prompt log); `test_no_key_leaks.py` parametrises over `LEAK_SURFACES`, so a new
surface becomes a new test case with no edit to the test.

Rule: define producers in `tests/security/planted.py` or a `tests/security/surfaces_*.py` module.
The registry is filled when `planted` is imported (it imports every `surfaces_*` module at its
end), which happens before the test module's `parametrize` reads it. A producer defined anywhere
else would register too late and never run.
"""

import base64
import contextlib
import importlib
import io
import json
import logging
import math
import pkgutil
import traceback
from collections.abc import Callable, Iterable, Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote, quote_plus

import pytest
from factories import FixedClock, loopback_client, make_settings
from pydantic import ValidationError
from sqlalchemy import text

from nosolear.api.app import create_app
from nosolear.budget.meter import Meter
from nosolear.cli import main
from nosolear.domain.budget import Caps, Provider, Unit
from nosolear.domain.errors import CapExceeded
from nosolear.domain.redaction import REDACTED
from nosolear.logging_setup import install_secret_scrubbing
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.ledger import SqliteUsageLedger
from nosolear.settings import REPO_ROOT, Settings, settings_error_summary

PLANTED_AZURE_KEY = "FAKEAZUREKEY" + "0123456789ABCDEFGHIJ"  # 32 chars
PLANTED_ANTHROPIC_KEY = "sk-ant-FAKEKEY" + "0123456789ABCDEFGHIJKLMNOP"  # 40 chars
PLANTED: tuple[str, ...] = (PLANTED_AZURE_KEY, PLANTED_ANTHROPIC_KEY)

Surface = Callable[[Path], tuple[str, str]]
LEAK_SURFACES: list[Surface] = []


def leak_surface(fn: Surface) -> Surface:
    """Register `fn(tmp_dir) -> (where, text)` as an output surface that must stay key-free."""
    LEAK_SURFACES.append(fn)
    return fn


def planted_settings(data_dir: Path, **overrides: Any) -> Settings:
    values: dict[str, Any] = {
        "data_dir": data_dir,
        "azure_speech_key": PLANTED_AZURE_KEY,
        "azure_speech_region": "westus2",
        "anthropic_api_key": PLANTED_ANTHROPIC_KEY,
    }
    values.update(overrides)
    return make_settings(**values)


def _b64_forms(key: str) -> dict[str, str]:
    """Base64 of the key at each of the three byte alignments it can take inside a longer text.

    The characters that mix in neighbouring bytes are trimmed, so what remains is a substring of
    the encoded text wherever the key sits in it.
    """
    forms: dict[str, str] = {}
    for urlsafe, encode in (("", base64.b64encode), ("-urlsafe", base64.urlsafe_b64encode)):
        for lead in range(3):
            encoded = encode(b"\0" * lead + key.encode()).decode().rstrip("=")
            head = math.ceil(lead * 4 / 3)
            forms[f"base64{urlsafe} (offset {lead})"] = encoded[head:-2]
    return forms


def _forms(key: str) -> dict[str, str]:
    forms = {
        "plain": key,
        "repr": repr(key),
        "repr (unquoted)": repr(key)[1:-1],
        "double-quoted": f'"{key}"',
        "url-encoded": quote(key, safe=""),
        "url-encoded (quote)": quote(key),
        "url-encoded (quote_plus)": quote_plus(key),
        "json-escaped": json.dumps(key),
        "json-escaped (unquoted)": json.dumps(key)[1:-1],
        "json-escaped (unicode)": json.dumps(key, ensure_ascii=False),
        "json-escaped (unicode, unquoted)": json.dumps(key, ensure_ascii=False)[1:-1],
    }
    forms.update(_b64_forms(key))
    return forms


def _form_table(keys: tuple[str, ...]) -> tuple[tuple[str, str], ...]:
    return tuple((name, form) for key in keys for name, form in _forms(key).items())


_SAFE_LEAVES = (int, float, bool, type(None))  # bool is an int; listed for the reader


def _texts(surface: object) -> list[str]:
    """Every piece of text that could show a key, failing closed on types it does not know.

    Strings and bytes are read directly; mappings, iterables (views, generators, rows, deques)
    and exception chains are walked; numbers and None are safe; anything else is scanned through
    both `str()` and `repr()`.
    """
    if isinstance(surface, str):
        return [surface]
    if isinstance(surface, (bytes, bytearray)):
        return [bytes(surface).decode("utf-8", errors="replace")]
    if isinstance(surface, _SAFE_LEAVES):
        return []
    found = [str(surface), repr(surface)]
    if isinstance(surface, Mapping):
        for k, v in surface.items():  # pyright: ignore[reportUnknownVariableType]
            found += _texts(k) + _texts(v)
    elif isinstance(surface, Iterable):
        found += [t for item in surface for t in _texts(item)]  # pyright: ignore[reportUnknownVariableType]
    if isinstance(surface, BaseException):
        found += [t for arg in surface.args for t in _texts(arg)]
        for linked in (surface.__cause__, surface.__context__):
            if linked is not None:
                found += _texts(linked)
    return found


def find_leak(*surfaces: object, keys: tuple[str, ...] = PLANTED) -> str | None:
    """The name of the first form of any of `keys` found in the surfaces, else None."""
    texts = [t for surface in surfaces for t in _texts(surface)]
    for name, form in _form_table(keys):
        if any(form in text for text in texts):
            return name
    return None


def assert_no_planted_key(*surfaces: object, where: str) -> None:
    """Fail, naming `where` and the form but never the key, if a planted key is in any surface."""
    form = find_leak(*surfaces)
    if form is not None:
        raise AssertionError(f"a planted key ({form} form) leaked through {where}")


# ---- surfaces ------------------------------------------------------------------------------


class LogCapture:
    """A real handler and Formatter on a private logger (or a named one), read back as text."""

    def __init__(self, formatter: logging.Formatter, name: str = "planted.capture") -> None:
        self.stream = io.StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(formatter)
        self.logger = logging.getLogger(name)

    def __enter__(self) -> LogCapture:
        self._state = (self.logger.level, self.logger.propagate)
        self.logger.addHandler(self.handler)
        self.logger.setLevel(logging.DEBUG)
        self.logger.propagate = False
        return self

    def __exit__(self, *exc: object) -> None:
        self.logger.removeHandler(self.handler)
        self.logger.setLevel(self._state[0])
        self.logger.propagate = self._state[1]

    @property
    def text(self) -> str:
        return self.stream.getvalue()


FORMAT = "%(levelname)s %(name)s %(message)s"


def _marked(text: str, *needles: str) -> str:
    """`text`, after checking the capture really saw a scrubbed record (not an empty capture)."""
    for needle in needles:
        assert needle in text, f"capture is missing {needle!r}"
    return text


@leak_surface
def settings_repr_str_dump_json(tmp: Path) -> tuple[str, str]:
    s = planted_settings(tmp)
    return "settings repr/str/model_dump/model_dump_json", "\n".join(
        [repr(s), str(s), repr(s.model_dump()), s.model_dump_json()]
    )


@leak_surface
def log_message_args_and_fstring(tmp: Path) -> tuple[str, str]:
    s = planted_settings(tmp)
    install_secret_scrubbing(s.secret_values())
    with LogCapture(logging.Formatter(FORMAT)) as cap:
        cap.logger.info("key=%s", PLANTED_AZURE_KEY)
        cap.logger.info("pair %s %s", PLANTED_ANTHROPIC_KEY, {"k": PLANTED_AZURE_KEY})
        cap.logger.info("named %(k)s", {"k": PLANTED_ANTHROPIC_KEY})
        cap.logger.info(f"fstring {PLANTED_AZURE_KEY} and {PLANTED_ANTHROPIC_KEY!r}")
        cap.logger.warning("object %s", s)
        cap.logger.info("quoted %r", PLANTED_AZURE_KEY)
    return "log messages and arguments", _marked(cap.text, REDACTED)


@leak_surface
def log_exception_with_key_in_message(tmp: Path) -> tuple[str, str]:
    s = planted_settings(tmp)
    install_secret_scrubbing(s.secret_values())
    with LogCapture(logging.Formatter(FORMAT)) as cap:
        try:
            raise RuntimeError(f"boom {PLANTED_AZURE_KEY}")
        except RuntimeError:
            cap.logger.exception("failed with %s", PLANTED_ANTHROPIC_KEY)
    return "log exception traceback", _marked(cap.text, "Traceback", REDACTED)


def _chained() -> RuntimeError:
    try:
        try:
            raise ValueError(PLANTED_ANTHROPIC_KEY)
        except ValueError as inner:
            raise RuntimeError(f"outer {PLANTED_AZURE_KEY}") from inner
    except RuntimeError as exc:
        return exc
    raise AssertionError("unreachable")


@leak_surface
def log_chained_exception(tmp: Path) -> tuple[str, str]:
    s = planted_settings(tmp)
    install_secret_scrubbing(s.secret_values())
    with LogCapture(logging.Formatter(FORMAT)) as cap:
        cap.logger.error("chained", exc_info=_chained())
    return "log chained exception traceback", _marked(
        cap.text, "Traceback", "direct cause", REDACTED
    )


class _SelfRenderingFormatter(logging.Formatter):
    """Stands in for JSON/structlog/Rich formatters: renders `exc_info` itself when it is set."""

    def format(self, record: logging.LogRecord) -> str:
        text = record.getMessage()
        if record.exc_info:
            text += "\n" + "".join(traceback.format_exception(*record.exc_info))
        elif record.exc_text:
            text += "\n" + record.exc_text
        return text


@leak_surface
def log_self_rendering_formatter(tmp: Path) -> tuple[str, str]:
    s = planted_settings(tmp)
    install_secret_scrubbing(s.secret_values())
    with LogCapture(_SelfRenderingFormatter()) as cap:
        cap.logger.error("chained", exc_info=_chained())
    return "log exception through a self-rendering formatter", _marked(
        cap.text, "Traceback", "direct cause", REDACTED
    )


@leak_surface
def uvicorn_unhandled_exception_log(tmp: Path) -> tuple[str, str]:
    """How uvicorn logs an unhandled exception, through its own formatter and logger."""
    from uvicorn.logging import DefaultFormatter

    settings = planted_settings(tmp)
    install_secret_scrubbing(settings.secret_values())
    formatter = DefaultFormatter(fmt="%(levelprefix)s %(message)s", use_colors=False)
    with LogCapture(formatter, name="uvicorn.error") as cap:
        cap.logger.error("Exception in ASGI application\n", exc_info=_chained())
    return "uvicorn.error unhandled exception log", _marked(
        cap.text, "Traceback", "direct cause", REDACTED
    )


# surfaces that go through the scrubbing installed by hand; the negative control disables it
SCRUBBED_LOG_SURFACES = (
    "log_message_args_and_fstring",
    "log_exception_with_key_in_message",
    "log_chained_exception",
    "log_self_rendering_formatter",
    "uvicorn_unhandled_exception_log",
)


@leak_surface
def lifespan_installs_scrubbing(tmp: Path) -> tuple[str, str]:
    """No hand-installed scrubbing: the app lifespan's `prepare_process` must do it."""
    app = create_app(planted_settings(tmp / "data"))
    with loopback_client(app), LogCapture(logging.Formatter(FORMAT), "nosolear.wiring") as cap:
        cap.logger.warning("config %s", PLANTED_AZURE_KEY)
        cap.logger.error("failed", exc_info=_chained())
    return "log records after the app lifespan started", _marked(cap.text, "Traceback", REDACTED)


@leak_surface
def cli_installs_scrubbing(tmp: Path) -> tuple[str, str]:
    """No hand-installed scrubbing: `main` must install it on the `db upgrade` path."""
    with pytest.MonkeyPatch.context() as mp:
        _planted_env(mp, tmp / "data")
        code, out, err = _run_cli(["db", "upgrade"])
    assert code == 0
    with LogCapture(logging.Formatter(FORMAT), "nosolear.wiring") as cap:
        cap.logger.warning("config %s", PLANTED_ANTHROPIC_KEY)
        cap.logger.error("failed", exc_info=_chained())
    return "log records after `nosolear db upgrade`", _marked(
        cap.text + out + err, "Traceback", REDACTED
    )


@leak_surface
def api_readiness_response(tmp: Path) -> tuple[str, str]:
    app = create_app(planted_settings(tmp / "data"))
    with loopback_client(app) as client:
        response = client.get("/api/readiness")
    assert response.status_code == 200
    assert response.text.count("key set") == 2, "the planted keys were not picked up"
    return "GET /api/readiness", response.text + repr(dict(response.headers))


@leak_surface
def api_health_and_profile_responses(tmp: Path) -> tuple[str, str]:
    app = create_app(planted_settings(tmp / "data"))
    parts: list[str] = []
    with loopback_client(app) as client:
        for path in ("/api/health", "/api/profile"):
            response = client.get(path)
            assert response.status_code == 200, path
            parts += [response.text, repr(dict(response.headers))]
    return "GET /api/health and /api/profile", "\n".join(parts)


@leak_surface
def openapi_schema(tmp: Path) -> tuple[str, str]:
    app = create_app(planted_settings(tmp / "data"))
    return "openapi schema", json.dumps(app.openapi())


@leak_surface
def api_unhandled_error_response(tmp: Path) -> tuple[str, str]:
    """The 500 a client sees. (TestClient logs nothing here; the uvicorn surface covers the log.)"""
    app = create_app(planted_settings(tmp / "data"))

    @app.get("/api/_boom")
    def boom() -> None:  # pyright: ignore[reportUnusedFunction]
        raise RuntimeError(f"boom {PLANTED_AZURE_KEY}")

    with loopback_client(app, raise_server_exceptions=False) as client:
        response = client.get("/api/_boom")
    assert response.status_code == 500
    return "unhandled error response", response.text + repr(dict(response.headers))


def _run_cli(argv: list[str]) -> tuple[int, str, str]:
    out, err = io.StringIO(), io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        code = main(argv)
    return code, out.getvalue(), err.getvalue()


def _planted_env(mp: pytest.MonkeyPatch, data_dir: Path, **extra: str) -> None:
    mp.setenv("NOSOLEAR_DATA_DIR", str(data_dir))
    mp.setenv("NOSOLEAR_AZURE_SPEECH_KEY", PLANTED_AZURE_KEY)
    mp.setenv("NOSOLEAR_AZURE_SPEECH_REGION", "westus2")
    mp.setenv("NOSOLEAR_ANTHROPIC_API_KEY", PLANTED_ANTHROPIC_KEY)
    for name, value in extra.items():
        mp.setenv(name, value)


@leak_surface
def doctor_output(tmp: Path) -> tuple[str, str]:
    with pytest.MonkeyPatch.context() as mp:
        _planted_env(mp, tmp / "data")
        code, out, err = _run_cli(["doctor"])
    assert code in (0, 1)
    assert out.count("key set") == 2, "the planted keys were not picked up"
    return "nosolear doctor stdout and stderr", out + err


@leak_surface
def validation_error_text(tmp: Path) -> tuple[str, str]:
    try:
        planted_settings(tmp, azure_speech_region=PLANTED_AZURE_KEY)
    except ValidationError as exc:
        assert [e["loc"] for e in exc.errors()] == [("azure_speech_region",)]
        return "settings ValidationError", str(exc) + repr(exc) + settings_error_summary(exc)
    raise AssertionError("a key in the region field must fail validation")


@leak_surface
def cli_bad_settings_stderr(tmp: Path) -> tuple[str, str]:
    with pytest.MonkeyPatch.context() as mp:
        _planted_env(mp, tmp / "data", NOSOLEAR_AZURE_SPEECH_REGION=PLANTED_ANTHROPIC_KEY)
        code, out, err = _run_cli(["doctor"])
    assert code == 2
    assert "NOSOLEAR_AZURE_SPEECH_REGION" in err
    return "cli invalid settings output", out + err


@leak_surface
def cli_data_dir_error_stderr(tmp: Path) -> tuple[str, str]:
    """`serve` with an unusable data dir exits before uvicorn starts, without echoing keys."""
    not_a_dir = tmp / "afile"
    not_a_dir.write_text("x")

    def fail(*args: object, **kwargs: object) -> None:
        raise AssertionError("uvicorn.run must not be reached")

    with pytest.MonkeyPatch.context() as mp:
        _planted_env(mp, not_a_dir)
        mp.setattr("uvicorn.run", fail)
        code, out, err = _run_cli(["serve"])
    assert code == 2
    assert "data directory problem" in err
    return "cli serve data-directory error output", out + err


@leak_surface
def env_example_and_repo_files(tmp: Path) -> tuple[str, str]:
    """Only the checked-in templates; the real `.env` is never opened."""
    names = (".env.example", "README.md")
    return "repo files (.env.example, README.md)", "\n".join(
        (REPO_ROOT / name).read_text(encoding="utf-8") for name in names
    )


@leak_surface
def usage_ledger_rows_and_cap_message(tmp: Path) -> tuple[str, str]:
    """Ledger rows after a refused reservation, and the CapExceeded the caller sees."""
    engine = create_engine_for(f"sqlite:///{tmp / 'ledger.sqlite'}")
    try:
        upgrade_to_head(engine)
        caps = Caps(azure_audio_seconds=10, azure_tts_chars=10, claude_tokens=10)
        ledger = SqliteUsageLedger(
            engine, caps=caps, clock=FixedClock(datetime(2026, 11, 13, tzinfo=UTC))
        )
        ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 4)
        refusal: CapExceeded | None = None
        try:
            ledger.reserve(Provider.ANTHROPIC, Unit.TOKENS, 11)
        except CapExceeded as exc:
            refusal = exc
        assert refusal is not None, "the over-cap reservation was not refused"
        with engine.connect() as conn:
            rows = [tuple(row) for row in conn.execute(text("SELECT * FROM usage_ledger"))]
    finally:
        engine.dispose()
    assert len(rows) == 1, "the refused reservation must not write a row"
    return "usage_ledger rows and CapExceeded", repr(rows) + str(refusal) + repr(refusal)


@leak_surface
def metered_failure_rows_and_log(tmp: Path) -> tuple[str, str]:
    """A paid call that fails with a key in its message: the ledger rows and the logged failure."""
    settings = planted_settings(tmp)
    install_secret_scrubbing(settings.secret_values())
    engine = create_engine_for(f"sqlite:///{tmp / 'metered.sqlite'}")
    try:
        upgrade_to_head(engine)
        caps = Caps(azure_audio_seconds=1000, azure_tts_chars=1000, claude_tokens=1000)
        ledger = SqliteUsageLedger(
            engine, caps=caps, clock=FixedClock(datetime(2026, 11, 13, tzinfo=UTC))
        )

        def fail() -> int:
            raise RuntimeError(PLANTED_AZURE_KEY)

        with LogCapture(logging.Formatter(FORMAT)) as cap:
            try:
                Meter(ledger).call(Provider.AZURE, Unit.AUDIO_SECONDS, 30, fail, actual=lambda n: n)
            except RuntimeError as exc:
                cap.logger.error("paid call failed", exc_info=exc)
        with engine.connect() as conn:
            rows = [tuple(row) for row in conn.execute(text("SELECT * FROM usage_ledger"))]
    finally:
        engine.dispose()
    assert len(rows) == 1, "the failed call must leave one settled row"
    return "metered call: usage_ledger rows and logged failure", repr(rows) + _marked(
        cap.text, "Traceback", REDACTED
    )


def _import_surface_modules() -> None:
    """Register every `surfaces_*` module's producers; must run after `leak_surface` exists."""
    for module in pkgutil.iter_modules([str(Path(__file__).parent)]):
        if module.name.startswith("surfaces_"):
            importlib.import_module(f"security.{module.name}")


_import_surface_modules()
