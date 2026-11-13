"""Maps typed errors to HTTP status codes and `ErrorOut` bodies (ARCHITECTURE.md section 8.1).

Every message is a literal sentence from the domain or from a route. Nothing here reads a
provider's text, a header or a key.
"""

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from nosolear.api.schemas import ErrorOut
from nosolear.domain.errors import (
    CapabilityMissing,
    CapExceeded,
    InvalidAudio,
    NosolearError,
    ProviderUnavailable,
)


class ApiError(Exception):
    """A route's own error: the status, the code and the literal message go to the client."""

    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def status_for(error: NosolearError) -> int:
    if isinstance(error, InvalidAudio):
        return {"too_large": 413, "bad_content_type": 415}.get(error.reason, 400)
    if isinstance(error, CapExceeded):
        return 429
    if isinstance(error, ProviderUnavailable):
        return 502
    if isinstance(error, CapabilityMissing):
        return 409
    return 500


def _json(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(ErrorOut(code=code, message=message).model_dump(), status_code=status_code)


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    def api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _json(exc.status_code, exc.code, exc.message)

    @app.exception_handler(NosolearError)
    def domain_error(request: Request, exc: NosolearError) -> JSONResponse:
        return _json(status_for(exc), exc.code, exc.safe_message)
