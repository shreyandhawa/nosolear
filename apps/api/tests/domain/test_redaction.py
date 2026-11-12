import json
from urllib.parse import quote, quote_plus

from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain.redaction import REDACTED, scrub
from nosolear.settings import MIN_KEY_LENGTH

TRICKY = 'a"b c/d+e&f\\g=hhhh'


def test_scrubs_a_secret() -> None:
    assert scrub("key=SECRETSECRET1", ["SECRETSECRET1"]) == "key=[redacted]"
    assert REDACTED == "[redacted]"


def test_empty_secret_is_ignored() -> None:
    assert scrub("hello", ["", "zzzzzzzzzzzzzzzz"]) == "hello"


def test_no_secrets_returns_text() -> None:
    assert scrub("anything at all", []) == "anything at all"


def test_url_quoted_forms() -> None:
    assert scrub(f"u?k={quote(TRICKY)}", [TRICKY]) == f"u?k={REDACTED}"
    assert scrub(f"u?k={quote(TRICKY, safe='')}", [TRICKY]) == f"u?k={REDACTED}"
    assert scrub(f"u?k={quote_plus(TRICKY)}", [TRICKY]) == f"u?k={REDACTED}"


def test_json_escaped_form() -> None:
    body = json.dumps({"k": TRICKY})
    assert TRICKY not in body
    assert scrub(body, [TRICKY]) == json.dumps({"k": REDACTED})


def test_repr_escaped_form() -> None:
    shown = repr(TRICKY)
    assert scrub(shown, [TRICKY]) == f"'{REDACTED}'"


def test_nested_secrets_are_both_removed() -> None:
    inner, outer = "abcdefghijklmnop", "abcdefghijklmnopQRST"
    assert scrub(f"{outer} {inner}", [inner, outer]) == f"{REDACTED} {REDACTED}"
    assert scrub(f"{outer} {inner}", [outer, inner]) == f"{REDACTED} {REDACTED}"


def test_quote_and_non_ascii_secret() -> None:
    for secret in ['it\'s "quoted" 0123456789', "clé-sécrète-ünï-0123456789"]:
        for form in (secret, quote(secret), quote_plus(secret), json.dumps(secret), repr(secret)):
            assert secret not in scrub(f"x {form} y", [secret])
            assert "[redacted]" in scrub(f"x {form} y", [secret])


_KEYS = st.text(min_size=MIN_KEY_LENGTH).filter(
    lambda s: not any(c.isspace() or c in "[]" for c in s)
)


@given(prefix=st.text(), suffix=st.text(), secret=_KEYS)
def test_secret_never_survives(prefix: str, suffix: str, secret: str) -> None:
    assert secret not in scrub(prefix + secret + suffix, [secret])


@given(secret=_KEYS, which=st.integers(0, 4))
def test_escaped_forms_never_survive(secret: str, which: int) -> None:
    form = [
        quote(secret),
        quote(secret, safe=""),
        quote_plus(secret),
        json.dumps(secret)[1:-1],
        repr(secret)[1:-1],
    ][which]
    assert form not in scrub(f"a {form} b", [secret])
