import json
from urllib.parse import quote, quote_plus

from hypothesis import assume, given
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


@given(
    prefix=st.text(),
    suffix=st.text(),
    secret=st.text(min_size=MIN_KEY_LENGTH).filter(lambda s: not any(c.isspace() for c in s)),
)
def test_secret_never_survives(prefix: str, suffix: str, secret: str) -> None:
    assume(REDACTED not in secret and secret not in REDACTED)
    assert secret not in scrub(prefix + secret + suffix, [secret])
