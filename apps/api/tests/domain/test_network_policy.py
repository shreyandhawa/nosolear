import pytest
from hypothesis import given
from hypothesis import strategies as st

from nosolear.domain import network_policy
from nosolear.domain.network_policy import (
    allowed_hosts,
    check_request,
    fetch_site_is_allowed,
    host_is_allowed,
    origin_is_allowed,
    peer_is_loopback,
)

DEFAULTS = ("http://localhost:5173", "http://127.0.0.1:5173")
ALLOWED = allowed_hosts(8000, DEFAULTS)
JUNK = st.text(alphabet=st.characters(min_codepoint=32, max_codepoint=126), min_size=1)


@pytest.mark.parametrize(
    "peer,ok",
    [
        ("127.0.0.1", True),
        ("127.5.5.5", True),
        ("::1", True),
        ("::ffff:127.0.0.1", True),
        ("::ffff:192.168.1.5", False),
        ("192.168.1.5", False),
        ("10.0.0.2", False),
        ("localhost", False),
        ("testclient", False),
        ("", False),
        (None, False),
    ],
)
def test_peer_is_loopback(peer: str | None, ok: bool) -> None:
    assert peer_is_loopback(peer) is ok


@pytest.mark.parametrize(
    "host,ok",
    [
        ("127.0.0.1:8000", True),
        ("localhost:8000", True),
        ("LOCALHOST:8000", True),
        ("[::1]:8000", True),
        ("localhost:5173", True),
        ("127.0.0.1.evil.com:8000", False),
        ("localhost:8000@evil.com", False),
        ("evil.com", False),
        ("localhost", False),
        ("localhost:9999", False),
        ("", False),
        (None, False),
        ("localhost:8000, evil.com", False),
    ],
)
def test_host_is_allowed(host: str | None, ok: bool) -> None:
    assert host_is_allowed(host, ALLOWED) is ok


@pytest.mark.parametrize(
    "origin,ok",
    [
        (None, True),
        ("http://localhost:5173", True),
        ("http://127.0.0.1:5173", True),
        ("null", False),
        ("http://localhost:5173.evil.com", False),
        ("http://localhost:5173/", False),
        ("https://localhost:5173", False),
        ("*", False),
        ("", False),
    ],
)
def test_origin_is_allowed(origin: str | None, ok: bool) -> None:
    assert origin_is_allowed(origin, DEFAULTS) is ok


@pytest.mark.parametrize(
    "value,ok",
    [
        ("same-origin", True),
        ("same-site", True),
        ("none", True),
        (" Same-Origin ", True),
        (None, True),
        ("cross-site", False),
        ("Cross-Site", False),
        ("cross-site ", False),
        ("bogus", False),
        ("", False),
    ],
)
def test_fetch_site_is_allowed(value: str | None, ok: bool) -> None:
    assert fetch_site_is_allowed(value) is ok


def _check(**kw: str | None) -> str | None:
    base: dict[str, str | None] = {
        "peer": "127.0.0.1",
        "host": "localhost:8000",
        "origin": None,
        "fetch_site": None,
    }
    base.update(kw)
    return check_request(port=8000, app_origins=DEFAULTS, **base)  # pyright: ignore[reportArgumentType]


def test_check_request_allows_a_clean_request() -> None:
    assert _check() is None


def test_check_request_reports_the_first_failing_reason() -> None:
    assert (
        _check(peer="10.0.0.2", host="evil.com", origin="null", fetch_site="cross-site") == "peer"
    )
    assert _check(host="evil.com", origin="null", fetch_site="cross-site") == "host"
    assert _check(origin="null", fetch_site="cross-site") == "origin"
    assert _check(fetch_site="cross-site") == "fetch_site"


@given(JUNK)
def test_origin_with_any_suffix_is_refused(junk: str) -> None:
    assert origin_is_allowed("http://localhost:5173" + junk, DEFAULTS) is False


@given(JUNK)
def test_host_with_any_suffix_is_refused(junk: str) -> None:
    assert host_is_allowed("localhost:8000" + junk, ALLOWED) is False


def test_null_origin_is_refused_even_if_configured() -> None:
    assert origin_is_allowed("null", ("null", *DEFAULTS)) is False


def test_allowed_hosts_for_a_custom_port_and_origins() -> None:
    hosts = allowed_hosts(9001, ["http://LOCALHOST:3000", "http://[::1]:3000"])
    assert hosts == {
        "127.0.0.1:9001",
        "localhost:9001",
        "[::1]:9001",
        "localhost:3000",
        "[::1]:3000",
    }


def test_check_request_builds_the_allowed_set_once() -> None:
    network_policy._allowed_hosts_cached.cache_clear()
    for _ in range(3):
        assert (
            check_request(
                peer="127.0.0.1",
                host="localhost:8000",
                origin=None,
                fetch_site=None,
                port=8000,
                app_origins=list(DEFAULTS),
            )
            is None
        )
    info = network_policy._allowed_hosts_cached.cache_info()
    assert (info.misses, info.hits) == (1, 2)
