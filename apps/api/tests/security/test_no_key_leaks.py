import json
from collections import deque
from dataclasses import dataclass

import pytest

from security.planted import (
    LEAK_SURFACES,
    PLANTED,
    PLANTED_ANTHROPIC_KEY,
    PLANTED_AZURE_KEY,
    SCRUBBED_LOG_SURFACES,
    assert_no_planted_key,
    find_leak,
    leak_surface,
)

EXPECTED_SURFACES = {
    "settings_repr_str_dump_json",
    "log_message_args_and_fstring",
    "log_exception_with_key_in_message",
    "log_chained_exception",
    "log_self_rendering_formatter",
    "uvicorn_unhandled_exception_log",
    "lifespan_installs_scrubbing",
    "cli_installs_scrubbing",
    "api_readiness_response",
    "api_health_and_profile_responses",
    "openapi_schema",
    "api_unhandled_error_response",
    "doctor_output",
    "validation_error_text",
    "cli_bad_settings_stderr",
    "cli_data_dir_error_stderr",
    "env_example_and_repo_files",
    "guard_refusal_response_and_log",
}


def _check(surface, tmp_path):
    """The body of the parametrised test; the negative tests run it too."""
    where, text = surface(tmp_path)
    assert text, f"{where} produced no output, so it proves nothing"
    assert_no_planted_key(text, where=where)


def test_registry_has_every_expected_surface():
    assert {fn.__name__ for fn in LEAK_SURFACES} >= EXPECTED_SURFACES


def test_leak_surface_returns_the_function_and_registers_it_once():
    def producer(tmp):
        return "x", "clean"

    try:
        assert leak_surface(producer) is producer
        assert LEAK_SURFACES.count(producer) == 1
    finally:
        LEAK_SURFACES.remove(producer)


def test_a_leaking_surface_fails_the_shared_check(tmp_path):
    def leaky(tmp):
        return "x", PLANTED_AZURE_KEY

    with pytest.raises(AssertionError, match="leaked through x"):
        _check(leaky, tmp_path)


def test_surfaces_modules_are_registered_and_collected(request):
    import importlib
    import inspect
    import pkgutil

    import security

    collected = {item.name for item in request.session.items}
    found = 0
    for module in pkgutil.iter_modules(security.__path__):
        if not module.name.startswith("surfaces_"):
            continue
        mod = importlib.import_module(f"security.{module.name}")
        for name, fn in inspect.getmembers(mod, inspect.isfunction):
            if fn.__module__ == mod.__name__ and not name.startswith("_"):
                found += 1
                assert fn in LEAK_SURFACES, name
                if any("test_no_planted_key_reaches" in n for n in collected):
                    assert any(f"[{name}]" in n for n in collected), name
    assert found >= 1


@pytest.mark.parametrize("surface", LEAK_SURFACES, ids=lambda fn: fn.__name__)
def test_no_planted_key_reaches_any_output_surface(surface, tmp_path):
    _check(surface, tmp_path)


@pytest.mark.parametrize("name", SCRUBBED_LOG_SURFACES)
def test_log_surfaces_fail_when_scrubbing_is_disabled(name, tmp_path, monkeypatch):
    """Negative control: the captures really see the records, so a clean pass means something."""
    import security.planted as planted

    monkeypatch.setattr(planted, "install_secret_scrubbing", lambda secrets: None)
    # Without scrubbing the captures lack the redaction marker, so stop the capture's own
    # non-vacuity check from tripping first: the leak assertion itself must be what fails.
    monkeypatch.setattr(planted, "_marked", lambda text, *needles: text)
    surface = next(fn for fn in LEAK_SURFACES if fn.__name__ == name)
    where, text = surface(tmp_path)
    with pytest.raises(AssertionError, match="a planted key .* leaked through"):
        assert_no_planted_key(text, where=where)


def test_assert_no_planted_key_detects_plain_quoted_and_urlencoded_forms():
    import base64
    from urllib.parse import quote, quote_plus

    for key in PLANTED:
        forms = {
            "plain": key,
            "repr": repr(key),
            "double-quoted": f'"{key}"',
            "url-encoded": quote(key, safe=""),
            "url-encoded-plus": quote_plus(key),
            "json": json.dumps(key),
            "base64": base64.b64encode(key.encode()).decode(),
            "base64-urlsafe": base64.urlsafe_b64encode(key.encode()).decode(),
        }
        for name, form in forms.items():
            with pytest.raises(AssertionError) as plain:
                assert_no_planted_key(f"prefix {form} suffix", where="here")
            assert "here" in str(plain.value)
            assert key not in str(plain.value)
            with pytest.raises(AssertionError):
                assert_no_planted_key({"a": [1, ("x", {"b": form})]}, where=f"nested {name}")
            with pytest.raises(AssertionError):
                assert_no_planted_key(form.encode(), where=f"bytes {name}")


def test_assert_no_planted_key_detects_shifted_base64():
    import base64

    for key in PLANTED:
        for prefix in (b"", b"a", b"ab", b"abc"):
            blob = base64.b64encode(prefix + key.encode() + b"tail!").decode()
            with pytest.raises(AssertionError):
                assert_no_planted_key(blob, where="b64")


def test_assert_no_planted_key_passes_clean_input_and_never_echoes_the_key():
    assert_no_planted_key(
        "nothing here", {"a": ["b", b"c", ("d",)]}, 3, 2.5, True, None, where="clean"
    )
    with pytest.raises(AssertionError) as err:
        assert_no_planted_key({"k": PLANTED_ANTHROPIC_KEY}, where="the-surface")
    message = str(err.value)
    assert "the-surface" in message
    assert all(key not in message for key in PLANTED)
    assert PLANTED_AZURE_KEY not in message


class _KeyRepr:
    def __repr__(self) -> str:
        return PLANTED_AZURE_KEY


@dataclass
class _Holder:
    value: str


def _generator():
    yield "ok"
    yield PLANTED_AZURE_KEY


HIDING_PLACES = {
    "dict values view": lambda: {"a": PLANTED_AZURE_KEY}.values(),
    "dict keys view": lambda: {PLANTED_AZURE_KEY: 1}.keys(),
    "generator": _generator,
    "deque": lambda: deque(["ok", PLANTED_AZURE_KEY]),
    "set": lambda: {PLANTED_AZURE_KEY},
    "object repr": _KeyRepr,
    "dataclass": lambda: _Holder(PLANTED_AZURE_KEY),
    "exception message": lambda: RuntimeError(f"boom {PLANTED_AZURE_KEY}"),
    "exception arg": lambda: RuntimeError("boom", {"k": PLANTED_AZURE_KEY}),
    "exception cause": lambda: _cause(),
    "nested iterator": lambda: iter([("ok", iter([PLANTED_AZURE_KEY]))]),
}


def _cause():
    try:
        raise RuntimeError("outer") from ValueError(PLANTED_AZURE_KEY)
    except RuntimeError as exc:
        return exc


@pytest.mark.parametrize("make", HIDING_PLACES.values(), ids=list(HIDING_PLACES))
def test_assert_no_planted_key_fails_closed_on_unusual_containers(make):
    with pytest.raises(AssertionError):
        assert_no_planted_key(make(), where="unusual")


def test_encoded_forms_are_distinct_from_plain_and_detected_when_embedded():
    key = 'ab/c+d \u00e9"efghijkl'
    forms = _forms_of(key)
    plain = forms.pop("plain")
    forms.pop("repr (unquoted)")  # equals the plain key here: repr leaves `"` alone in '...'
    assert forms and all(form != plain for form in forms.values())
    for name, form in forms.items():
        assert find_leak(f"x {form} y", keys=(key,)) is not None, name
    assert find_leak("nothing to see here", keys=(key,)) is None


def _forms_of(key):
    from security.planted import _forms

    return _forms(key)
