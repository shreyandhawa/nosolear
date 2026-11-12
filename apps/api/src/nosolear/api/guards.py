"""Outermost ASGI guard: refuse anything that is not a loopback request from the app itself."""

import logging
from collections.abc import Sequence

from starlette.responses import JSONResponse
from starlette.types import ASGIApp, Receive, Scope, Send

from nosolear.domain.network_policy import allowed_hosts, check_request

logger = logging.getLogger(__name__)

_REFUSAL = {"detail": "request refused"}
_WS_POLICY_VIOLATION = 1008


def _single_header(scope: Scope, name: bytes) -> tuple[str | None, bool]:
    """The header's value and whether it appeared more than once (never legitimate)."""
    values = [v for k, v in scope.get("headers", ()) if k == name]
    if not values:
        return None, False
    return values[0].decode("latin-1"), len(values) > 1


class RequestGuardMiddleware:
    def __init__(self, app: ASGIApp, *, port: int, app_origins: Sequence[str]) -> None:
        self._app = app
        self._port = port
        self._app_origins = tuple(app_origins)
        # built once so the per-request check stays cheap
        self._allowed_hosts = allowed_hosts(port, self._app_origins)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] not in ("http", "websocket"):
            await self._app(scope, receive, send)
            return
        reason = self._refusal_reason(scope)
        if reason is None:
            await self._app(scope, receive, send)
            return
        # reason code and path only: never a header value or the peer address
        logger.warning("refused %s request: %s (path %s)", scope["type"], reason, scope["path"])
        if scope["type"] == "websocket":
            await send({"type": "websocket.close", "code": _WS_POLICY_VIOLATION})
            return
        await JSONResponse(_REFUSAL, status_code=403)(scope, receive, send)

    def _refusal_reason(self, scope: Scope) -> str | None:
        client = scope.get("client")
        peer = client[0] if client else None
        host, host_dup = _single_header(scope, b"host")
        origin, origin_dup = _single_header(scope, b"origin")
        fetch_site, fetch_dup = _single_header(scope, b"sec-fetch-site")
        return check_request(
            peer=peer,
            host="" if host_dup else host,
            origin="" if origin_dup else origin,
            fetch_site="cross-site" if fetch_dup else fetch_site,
            port=self._port,
            app_origins=self._app_origins,
        )
