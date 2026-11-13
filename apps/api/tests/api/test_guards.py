import asyncio
import logging
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import pytest
from factories import loopback_client, make_settings
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nosolear.api.app import create_app
from nosolear.api.guards import RequestGuardMiddleware

REFUSED = {"detail": "request refused"}
ORIGIN = "http://localhost:5173"
# TestClient ignores base_url for websockets, so the loopback Host must be in the URL
WS_URL = "ws://127.0.0.1:8000/ws-test"
READ_ONLY_GET_ROUTES = {
    "/api/health",
    "/api/profile",
    "/api/readiness",
    "/api/jobs/{job_id}",
    "/api/calibration",
    "/api/baseline",
    "/api/baseline/report",
    "/api/onboarding",
}  # later phases add theirs


# Swagger UI and ReDoc load scripts from a CDN, so they are disabled; the schema itself is kept.
DOCS_ROUTES = {"/openapi.json"}


def _all_get_paths(app: Any) -> set[str]:
    """Every GET path in the real route table, including hidden ones (private attrs are fine)."""

    def walk(routes: Any, prefix: str) -> Iterator[str]:
        for route in routes:
            inner = getattr(route, "original_router", None)
            if inner is not None:
                yield from walk(inner.routes, prefix + route.include_context.prefix)
            elif hasattr(route, "routes"):  # a Mount
                yield from walk(route.routes, prefix + getattr(route, "path", ""))
            elif "GET" in (getattr(route, "methods", None) or ()):
                yield prefix + route.path

    return set(walk(app.routes, ""))


@pytest.fixture
def app(tmp_path: Path) -> FastAPI:
    return create_app(make_settings(data_dir=tmp_path))


def test_loopback_peer_and_host_pass(app: FastAPI) -> None:
    with loopback_client(app) as c:
        assert c.get("/api/health").status_code == 200


def test_non_loopback_peer_refused(app: FastAPI) -> None:
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("192.168.1.5", 4000)) as c:
        for path in ("/api/health", "/api/profile"):
            r = c.get(path)
            assert r.status_code == 403
            assert r.json() == REFUSED


def test_missing_client_is_refused(app: FastAPI) -> None:
    with TestClient(app, base_url="http://127.0.0.1:8000", client=None) as c:  # pyright: ignore[reportArgumentType]
        assert c.get("/api/health").status_code == 403


@pytest.mark.parametrize("host", ["evil.com", "127.0.0.1.evil.com:8000", "localhost:8000@evil.com"])
def test_foreign_host_refused(app: FastAPI, host: str) -> None:
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Host": host}).status_code == 403


def test_default_testserver_host_refused(app: FastAPI) -> None:
    with TestClient(app, client=("127.0.0.1", 50000)) as c:
        assert c.get("/api/health").status_code == 403


def test_duplicate_host_header_refused(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.get("/api/health", headers=[("Host", "localhost:8000"), ("Host", "localhost:8000")])
        assert r.status_code == 403


def test_duplicate_origin_header_refused(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.get("/api/health", headers=[("Origin", ORIGIN), ("Origin", ORIGIN)])
        assert r.status_code == 403


def test_vite_proxy_host_allowed(app: FastAPI) -> None:
    # The Vite proxy keeps the browser's Host (changeOrigin: false), so this is what it sends.
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Host": "localhost:5173"}).status_code == 200


@pytest.mark.parametrize("path", ["/docs", "/redoc", "/docs/oauth2-redirect"])
def test_interactive_docs_are_not_served(app: FastAPI, path: str) -> None:
    with loopback_client(app) as c:
        assert c.get(path).status_code == 404


def test_openapi_schema_is_still_served(app: FastAPI) -> None:
    with loopback_client(app) as c:
        assert c.get("/openapi.json").status_code == 200


def test_origin_null_refused(app: FastAPI) -> None:
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Origin": "null"}).status_code == 403


def test_foreign_origin_refused_on_post_and_get(app: FastAPI) -> None:
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Origin": "http://evil.com"}).status_code == 403
        assert c.post("/api/profile", headers={"Origin": "http://evil.com"}).status_code == 403


def test_allowed_origin_passes(app: FastAPI) -> None:
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Origin": ORIGIN}).status_code == 200


def test_sec_fetch_site_cross_site_refused(app: FastAPI) -> None:
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Sec-Fetch-Site": "cross-site"}).status_code == 403
        assert c.get("/api/health", headers={"Sec-Fetch-Site": "same-site"}).status_code == 200


def test_refusal_body_is_fixed_and_leaks_nothing(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.get("/api/health", headers={"Host": "secret-marker.evil.com"})
    assert r.status_code == 403
    assert r.json() == REFUSED
    assert "secret-marker" not in r.text


def test_refusal_log_has_reason_only(app: FastAPI, caplog: pytest.LogCaptureFixture) -> None:
    with (
        caplog.at_level(logging.WARNING),
        TestClient(app, base_url="http://127.0.0.1:8000", client=("192.168.7.7", 4000)) as c,
    ):
        c.get("/api/health", headers={"Origin": "http://secret-marker.evil.com"})
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "peer" in text
    assert "secret-marker" not in text
    assert "192.168.7.7" not in text


def test_cors_preflight_for_allowed_origin_only(app: FastAPI) -> None:
    with loopback_client(app) as c:
        ok = c.options(
            "/api/profile",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )
        assert ok.status_code == 200
        assert ok.headers["access-control-allow-origin"] == ORIGIN
        bad = c.options(
            "/api/profile",
            headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "POST"},
        )
        assert bad.status_code == 403
        assert "access-control-allow-origin" not in bad.headers


def test_cors_never_wildcard(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.get("/api/health", headers={"Origin": ORIGIN})
        assert r.headers["access-control-allow-origin"] != "*"
        assert "access-control-allow-credentials" not in r.headers


def test_no_cookies_set(app: FastAPI) -> None:
    with loopback_client(app) as c:
        for r in (
            c.get("/api/health"),
            c.get("/api/health", headers={"Origin": ORIGIN}),
            c.get("/api/health", headers={"Host": "evil.com"}),
        ):
            assert "set-cookie" not in r.headers


def test_get_routes_are_declared_read_only(app: FastAPI) -> None:
    # FastAPI wraps included routers lazily, so read the schema here and the real table below
    gets = {path for path, ops in app.openapi()["paths"].items() if "get" in ops}
    assert gets == READ_ONLY_GET_ROUTES
    assert _all_get_paths(app) == READ_ONLY_GET_ROUTES | DOCS_ROUTES


def test_route_walker_sees_a_hidden_get_route(tmp_path: Path) -> None:
    hidden = create_app(make_settings(data_dir=tmp_path))

    @hidden.get("/api/x", include_in_schema=False)
    def x() -> dict[str, str]:  # pyright: ignore[reportUnusedFunction]
        return {}

    assert "/api/x" not in hidden.openapi()["paths"]
    assert "/api/x" in _all_get_paths(hidden)
    assert _all_get_paths(hidden) != READ_ONLY_GET_ROUTES | DOCS_ROUTES


def _ws_app(app: FastAPI) -> FastAPI:
    @app.websocket("/ws-test")
    async def ws(socket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        await socket.accept()
        await socket.send_text("hi")
        await socket.close()

    return app


def test_websocket_refused_for_foreign_origin(app: FastAPI) -> None:
    app = _ws_app(app)
    with (
        loopback_client(app) as c,
        pytest.raises(WebSocketDisconnect) as exc,
        c.websocket_connect(WS_URL, headers={"Origin": "http://evil.com"}),
    ):
        pass
    assert exc.value.code == 1008


def test_websocket_allowed_for_loopback(app: FastAPI) -> None:
    app = _ws_app(app)
    with loopback_client(app) as c, c.websocket_connect(WS_URL) as ws:
        assert ws.receive_text() == "hi"


# --- configured port and origins -------------------------------------------------------------


@pytest.fixture
def custom_app(tmp_path: Path) -> FastAPI:
    return create_app(
        make_settings(data_dir=tmp_path, port=9001, app_origins=["http://localhost:3000"])
    )


def test_custom_port_and_origin_are_honoured(custom_app: FastAPI) -> None:
    with loopback_client(custom_app, port=9001) as c:
        assert c.get("/api/health", headers={"Host": "localhost:9001"}).status_code == 200
        assert c.get("/api/health", headers={"Host": "localhost:8000"}).status_code == 403
        allowed = c.get("/api/health", headers={"Origin": "http://localhost:3000"})
        assert allowed.status_code == 200
        assert allowed.headers["access-control-allow-origin"] == "http://localhost:3000"
        assert c.get("/api/health", headers={"Origin": ORIGIN}).status_code == 403
        pre = c.options(
            "/api/profile",
            headers={"Origin": "http://localhost:3000", "Access-Control-Request-Method": "POST"},
        )
        assert pre.status_code == 200
        assert pre.headers["access-control-allow-origin"] == "http://localhost:3000"


# --- extra refusal cases ---------------------------------------------------------------------


def test_duplicate_sec_fetch_site_refused(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.get(
            "/api/health",
            headers=[("Sec-Fetch-Site", "same-origin"), ("Sec-Fetch-Site", "same-origin")],
        )
        assert r.status_code == 403


def test_duplicate_host_with_differing_values_refused(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.get("/api/health", headers=[("Host", "localhost:8000"), ("Host", "evil.com")])
        assert r.status_code == 403


@pytest.mark.parametrize(
    "case",
    [
        {"client": ("192.168.1.5", 4000)},
        {"host": "evil.com"},
        {"origin": "http://evil.com"},
    ],
)
def test_websocket_refusal_never_runs_the_handler(app: FastAPI, case: dict[str, Any]) -> None:
    ran: list[bool] = []

    @app.websocket("/ws-test")
    async def ws(socket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        ran.append(True)
        await socket.accept()

    url = f"ws://{case.get('host', '127.0.0.1:8000')}/ws-test"
    headers = {"Origin": case["origin"]} if "origin" in case else {}
    client = TestClient(app, client=case.get("client", ("127.0.0.1", 50000)))
    with (
        client,
        pytest.raises(WebSocketDisconnect) as exc,
        client.websocket_connect(url, headers=headers),
    ):
        pass
    assert exc.value.code == 1008
    assert ran == []


@pytest.mark.parametrize(
    "headers,reason",
    [
        ({"Host": "secret-marker.evil.com"}, "host"),
        ({"Origin": "http://secret-marker.evil.com"}, "origin"),
    ],
)
def test_refusal_log_for_host_and_origin_has_reason_only(
    app: FastAPI, caplog: pytest.LogCaptureFixture, headers: dict[str, str], reason: str
) -> None:
    with caplog.at_level(logging.WARNING), loopback_client(app) as c:
        assert c.get("/api/health", headers=headers).status_code == 403
    text = " ".join(r.getMessage() for r in caplog.records)
    assert reason in text
    assert "secret-marker" not in text


def test_refusal_log_escapes_the_path(app: FastAPI, caplog: pytest.LogCaptureFixture) -> None:
    with caplog.at_level(logging.WARNING), loopback_client(app) as c:
        assert c.get("/%1b]52;x%0a%0dINFO:forged", headers={"Host": "evil.com"}).status_code == 403
    guard_logs = [r.getMessage() for r in caplog.records if r.name.endswith("guards")]
    assert guard_logs
    for message in guard_logs:
        assert not any(ch in message for ch in ("\x1b", "\n", "\r"))
        assert "\\x1b" in message  # shown escaped, not raw


def test_preflight_from_non_loopback_peer_gets_no_cors_headers(app: FastAPI) -> None:
    with TestClient(app, base_url="http://127.0.0.1:8000", client=("10.0.0.2", 1)) as c:
        r = c.options(
            "/api/profile",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )
    assert r.status_code == 403
    assert r.json() == REFUSED
    assert not [h for h in r.headers if h.startswith("access-control-allow")]


def test_preflight_with_foreign_host_gets_no_cors_headers(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.options(
            "/api/profile",
            headers={
                "Host": "evil.com",
                "Origin": ORIGIN,
                "Access-Control-Request-Method": "POST",
            },
        )
    assert r.status_code == 403
    assert r.json() == REFUSED
    assert not [h for h in r.headers if h.startswith("access-control-allow")]


@pytest.mark.parametrize(
    "extra",
    [
        {"Access-Control-Request-Method": "PATCH"},
        {
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization",
        },
    ],
)
def test_preflight_does_not_grant_other_methods_or_headers(
    app: FastAPI, extra: dict[str, str]
) -> None:
    with loopback_client(app) as c:
        r = c.options("/api/profile", headers={"Origin": ORIGIN, **extra})
    assert r.status_code == 400
    assert "PATCH" not in r.headers.get("access-control-allow-methods", "")
    assert "authorization" not in r.headers.get("access-control-allow-headers", "").lower()


def test_allowed_preflight_has_no_credentials_header(app: FastAPI) -> None:
    with loopback_client(app) as c:
        r = c.options(
            "/api/profile",
            headers={"Origin": ORIGIN, "Access-Control-Request-Method": "POST"},
        )
    assert r.status_code == 200
    assert "access-control-allow-credentials" not in r.headers


# --- the middleware on raw ASGI scopes ---------------------------------------------------------


def _run_guard(scope_type: str, headers: list[tuple[bytes, bytes]]) -> tuple[list[Any], bool]:
    called: list[bool] = []
    sent: list[Any] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        called.append(True)

    async def receive() -> Any:
        return {"type": "http.request"}

    async def send(message: Any) -> None:
        sent.append(message)

    guard = RequestGuardMiddleware(inner, port=8000, app_origins=("http://localhost:5173",))
    scope = {
        "type": scope_type,
        "path": "/api/health",
        "client": ("127.0.0.1", 1),
        "headers": headers,
    }
    asyncio.run(guard(scope, receive, send))
    return sent, bool(called)


GOOD_HOST = (b"host", b"localhost:8000")


@pytest.mark.parametrize(
    "headers",
    [
        [(b"host", b"")],
        [],
        [(b"host", "localhost:8000\xe9".encode("latin-1"))],
        [GOOD_HOST, (b"origin", b"")],
        [GOOD_HOST, (b"origin", b"HTTP://LOCALHOST:5173")],
    ],
    ids=["empty-host", "missing-host", "latin1-host", "empty-origin", "upper-case-origin"],
)
def test_malformed_headers_are_refused(headers: list[tuple[bytes, bytes]]) -> None:
    sent, called = _run_guard("http", headers)
    assert not called
    assert sent[0]["status"] == 403


def test_clean_scope_reaches_the_app() -> None:
    _, called = _run_guard("http", [GOOD_HOST])
    assert called


def test_lifespan_passes_through_and_unknown_scope_types_are_dropped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    _, called = _run_guard("lifespan", [])
    assert called
    with caplog.at_level(logging.WARNING):
        sent, called = _run_guard("bogus-type", [GOOD_HOST])
    assert not called
    assert sent == []
    assert "bogus-type" in " ".join(r.getMessage() for r in caplog.records)
