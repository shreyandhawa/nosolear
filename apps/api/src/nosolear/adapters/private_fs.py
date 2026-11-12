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
    try:
        path.mkdir(mode=DIR_MODE, parents=True, exist_ok=True)
        if os.stat(path).st_uid != os.getuid():
            raise DataDirError(f"{path} is owned by another user; choose a directory you own")
        os.chmod(path, DIR_MODE)
        if stat.S_IMODE(os.stat(path).st_mode) != DIR_MODE:
            raise DataDirError(f"{path} would not accept owner-only permissions (0700)")
    except OSError as exc:
        raise DataDirError(f"cannot prepare {path}: {exc.strerror or exc}") from exc


def tighten_tree(path: Path) -> None:
    """Make `path` and the directories under it 0700, files 0600. Symlinks are left alone.

    Entries that vanish mid-walk (transient SQLite files) are skipped; any other failure is
    collected and raised together as one `DataDirError`.
    """
    failed: list[str] = []

    def chmod(entry: str, directory: bool) -> None:
        try:
            if not stat.S_ISLNK(os.lstat(entry).st_mode):
                os.chmod(entry, DIR_MODE if directory else FILE_MODE)
        except FileNotFoundError:
            pass
        except OSError as exc:
            failed.append(f"{entry} ({exc.strerror or exc})")

    chmod(str(path), True)
    for root, dirs, files in os.walk(path, followlinks=False):
        for name in dirs:
            chmod(os.path.join(root, name), True)
        for name in files:
            chmod(os.path.join(root, name), False)
    if failed:
        raise DataDirError("cannot restrict permissions on: " + "; ".join(failed))


def make_private_file(path: Path) -> None:
    os.chmod(path, FILE_MODE)
