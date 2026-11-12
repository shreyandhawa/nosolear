import json

import pytest

from security.planted import (
    LEAK_SURFACES,
    PLANTED,
    PLANTED_ANTHROPIC_KEY,
    PLANTED_AZURE_KEY,
    assert_no_planted_key,
)


def test_registry_is_not_empty():
    assert len(LEAK_SURFACES) >= 10


@pytest.mark.parametrize("surface", LEAK_SURFACES, ids=lambda fn: fn.__name__)
def test_no_planted_key_reaches_any_output_surface(surface, tmp_path):
    where, text = surface(tmp_path)
    assert text, f"{where} produced no output, so it proves nothing"
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
    assert_no_planted_key("nothing here", {"a": ["b", b"c", ("d",)]}, 3, None, where="clean")
    with pytest.raises(AssertionError) as err:
        assert_no_planted_key({"k": PLANTED_ANTHROPIC_KEY}, where="the-surface")
    message = str(err.value)
    assert "the-surface" in message
    assert all(key not in message for key in PLANTED)
    assert PLANTED_AZURE_KEY not in message
