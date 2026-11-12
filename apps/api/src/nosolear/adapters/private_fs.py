"""Owner-only permissions for the data directory and the files in it."""

import os
import stat
from pathlib import Path

DIR_MODE = 0o700
FILE_MODE = 0o600


class DataDirError(RuntimeError):
    """The data directory is not safe to use."""


def ensure_private_dir(path: Path) -> None:
    """Create `path` (and parents) if needed and make it 0700; refuse one owned by another user."""
    path.mkdir(parents=True, exist_ok=True)
    if os.stat(path).st_uid != os.getuid():
        raise DataDirError(f"{path} is owned by another user; choose a directory you own")
    os.chmod(path, DIR_MODE)


def tighten_tree(path: Path) -> None:
    """Make `path` and the directories under it 0700, files 0600. Symlinks are left alone."""
    if not path.is_symlink():
        os.chmod(path, DIR_MODE)
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in [*dirs, *files]:
            entry = os.path.join(root, name)
            mode = os.lstat(entry).st_mode
            if stat.S_ISLNK(mode):
                continue
            os.chmod(entry, DIR_MODE if stat.S_ISDIR(mode) else FILE_MODE)


def make_private_file(path: Path) -> None:
    os.chmod(path, FILE_MODE)
