"""What the machine offers, so readiness never imports a model library or reads a file."""

from pathlib import Path
from typing import Protocol


class EnvironmentProbe(Protocol):
    def module_available(self, name: str) -> bool: ...

    def executable_available(self, name: str) -> bool: ...

    def path_mode(self, path: Path) -> int | None:
        """Permission bits (`& 0o777`), or None when the path does not exist."""
        ...

    def platform(self) -> tuple[str, str]:
        """(`sys.platform`-style system, machine)."""
        ...
