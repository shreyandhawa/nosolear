import logging
from pathlib import Path

import pytest
from factories import loopback_client, make_settings
from fastapi import FastAPI, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from nosolear.api.app import create_app

REFUSED = {"detail": "request refused"}
ORIGIN = "http://localhost:5173"
# TestClient ignores base_url for websockets, so the loopback Host must be in the URL
WS_URL = "ws://127.0.0.1:8000/ws-test"
READ_ONLY_GET_ROUTES = {"/api/health", "/api/profile", "/api/readiness"}  # later phases add theirs


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
    with loopback_client(app) as c:
        assert c.get("/api/health", headers={"Host": "localhost:5173"}).status_code == 200


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
    # FastAPI wraps included routers lazily, so read the route table from the OpenAPI schema
    gets = {path for path, ops in app.openapi()["paths"].items() if "get" in ops}
    assert gets == READ_ONLY_GET_ROUTES


def _ws_app(app: FastAPI) -> FastAPI:
    @app.websocket("/ws-test")
    async def ws(socket: WebSocket) -> None:  # pyright: ignore[reportUnusedFunction]
        await socket.accept()
        await socket.send_text("hi")
        await socket.close()

    return app


def test_websocket_refused_for_foreign_origin(app: FastAPI) -> None:
    # the route must be added before middleware is built, i.e. before the first request
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
