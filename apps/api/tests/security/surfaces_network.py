"""Network-guard surfaces. Producers in `surfaces_*` modules are registered by `planted`."""

import logging
from pathlib import Path

from factories import loopback_client

from nosolear.api.app import create_app
from nosolear.domain.redaction import REDACTED
from nosolear.logging_setup import install_secret_scrubbing
from security.planted import (
    FORMAT,
    PLANTED_AZURE_KEY,
    LogCapture,
    leak_surface,
    planted_settings,
)


@leak_surface
def guard_refusal_response_and_log(tmp: Path) -> tuple[str, str]:
    """A refused request whose path carries a key: the 403 body and the guard's log stay clean."""
    settings = planted_settings(tmp / "data")
    install_secret_scrubbing(settings.secret_values())
    client = loopback_client(create_app(settings))
    with LogCapture(logging.Formatter(FORMAT), "nosolear.api.guards") as cap:
        response = client.get(f"/{PLANTED_AZURE_KEY}", headers={"Host": "evil.com"})
    assert response.status_code == 403
    assert REDACTED in cap.text, "the guard log did not carry the scrubbed path"
    return "guard refusal response and log", response.text + repr(dict(response.headers)) + cap.text
