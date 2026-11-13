import logging

from nosolear.logging_setup import QUIET_LOGGERS
from nosolear.settings import Settings


def test_a_live_run_gets_the_cli_process_setup(live_settings: Settings) -> None:
    # Live tests hold real keys, so they run the same setup as the CLI and server: the secret
    # scrubber's log record factory and the client loggers pinned to WARNING. No live call is made.
    assert logging.getLogRecordFactory().__module__ == "nosolear.logging_setup"
    for name in QUIET_LOGGERS:
        assert logging.getLogger(name).level == logging.WARNING, name
