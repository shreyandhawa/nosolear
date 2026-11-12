import importlib.util
import os
import platform
import shutil
import sys
from pathlib import Path


class SystemEnvironment:
    def module_available(self, name: str) -> bool:
        try:
            return importlib.util.find_spec(name) is not None
        except ImportError, ValueError:  # a dotted name whose parent package is missing
            return False

    def executable_available(self, name: str) -> bool:
        return shutil.which(name) is not None

    def path_mode(self, path: Path) -> int | None:
        try:
            return os.stat(path).st_mode & 0o777
        except OSError:
            return None

    def platform(self) -> tuple[str, str]:
        return sys.platform, platform.machine()
