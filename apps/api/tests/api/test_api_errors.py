from pathlib import Path

import pytest
from factories import loopback_client, make_settings

from nosolear.api.app import create_app
from nosolear.domain.errors import (
    CapabilityMissing,
    CapExceeded,
    InvalidAudio,
    NosolearError,
    ProviderUnavailable,
)


@pytest.mark.parametrize(
    ("error", "status", "code", "message"),
    [
        (
            InvalidAudio("too_large"),
            413,
            "invalid_audio",
            "The recording is larger than the 10 MB upload limit.",
        ),
        (
            InvalidAudio("bad_content_type"),
            415,
            "invalid_audio",
            "The upload must be sent as audio/wav.",
        ),
        (InvalidAudio("not_wav"), 400, "invalid_audio", "The upload is not a WAV file."),
        (
            CapExceeded(),
            429,
            "cap_exceeded",
            "The usage cap for this period would be exceeded.",
        ),
        (
            ProviderUnavailable(),
            502,
            "provider_unavailable",
            "The speech or language provider is unavailable.",
        ),
        (
            CapabilityMissing(),
            409,
            "capability_missing",
            "This capability is not available in the current setup.",
        ),
    ],
)
def test_domain_errors_map_to_status_code_and_safe_body(
    tmp_path: Path, error: NosolearError, status: int, code: str, message: str
) -> None:
    app = create_app(make_settings(data_dir=tmp_path), start_runner=False)

    @app.get("/api/_raise")
    def raise_error() -> None:  # pyright: ignore[reportUnusedFunction]
        raise error

    with loopback_client(app) as client:
        r = client.get("/api/_raise")
    assert r.status_code == status
    assert r.json() == {"code": code, "message": message}
