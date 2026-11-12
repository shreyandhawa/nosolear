"""Process-wide setup shared by the CLI and the API server."""

import os

from nosolear.adapters.private_fs import ensure_private_dir, tighten_tree
from nosolear.logging_setup import install_secret_scrubbing
from nosolear.settings import Settings


def prepare_process(settings: Settings, *, create_data_dir: bool) -> None:
    install_secret_scrubbing(settings.secret_values())
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    if create_data_dir:
        os.umask(0o077)  # new files (SQLite, audio) are owner-only from creation
        ensure_private_dir(settings.data_dir)
        tighten_tree(settings.data_dir)
