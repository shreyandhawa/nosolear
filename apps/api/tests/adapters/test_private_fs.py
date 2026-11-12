import os
import stat
from pathlib import Path

import pytest

from nosolear.adapters.private_fs import (
    DataDirError,
    ensure_private_dir,
    make_private_file,
    tighten_tree,
)


def mode(path: Path) -> int:
    return stat.S_IMODE(path.stat().st_mode)


def test_tighten_tree(tmp_path: Path) -> None:
    root = tmp_path / "d"
    nested = root / "n"
    nested.mkdir(parents=True)
    file = root / "f.txt"
    file.write_text("x")
    root.chmod(0o755)
    nested.chmod(0o755)
    file.chmod(0o644)
    tighten_tree(root)
    assert (mode(root), mode(nested), mode(file)) == (0o700, 0o700, 0o600)


def test_ensure_creates_nested_private(tmp_path: Path) -> None:
    target = tmp_path / "a" / "b"
    ensure_private_dir(target)
    assert mode(target) == 0o700


def test_ensure_tightens_existing(tmp_path: Path) -> None:
    target = tmp_path / "d"
    target.mkdir()
    target.chmod(0o755)
    ensure_private_dir(target)
    assert mode(target) == 0o700


def test_ensure_rejects_foreign_owner(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    target = tmp_path / "d"
    target.mkdir()
    real_stat = os.stat

    def fake(path: object, *args: object, **kw: object) -> os.stat_result:
        result = real_stat(path, *args, **kw)  # pyright: ignore[reportArgumentType]
        if Path(str(path)) == target:
            fields = list(result)
            fields[4] = os.getuid() + 1
            return os.stat_result(fields)
        return result

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "stat", fake)
        with pytest.raises(DataDirError):
            ensure_private_dir(target)


def test_symlinks_are_not_followed(tmp_path: Path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    outside.chmod(0o755)
    secret = outside / "f"
    secret.write_text("x")
    secret.chmod(0o644)
    root = tmp_path / "root"
    root.mkdir()
    (root / "dirlink").symlink_to(outside, target_is_directory=True)
    (root / "filelink").symlink_to(secret)
    tighten_tree(root)
    assert mode(outside) == 0o755
    assert mode(secret) == 0o644


def test_make_private_file(tmp_path: Path) -> None:
    file = tmp_path / "f"
    file.write_text("x")
    file.chmod(0o644)
    make_private_file(file)
    assert mode(file) == 0o600
