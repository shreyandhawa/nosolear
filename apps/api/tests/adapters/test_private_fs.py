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


def test_foreign_owner_leaves_mode_unchanged(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    target = tmp_path / "d"
    target.mkdir()
    target.chmod(0o755)
    real_stat = os.stat

    def fake(path: object, *args: object, **kw: object) -> os.stat_result:
        result = real_stat(path, *args, **kw)  # pyright: ignore[reportArgumentType]
        fields = list(result)
        fields[4] = os.getuid() + 1
        return os.stat_result(fields)

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "stat", fake)
        with pytest.raises(DataDirError):
            ensure_private_dir(target)
    assert mode(target) == 0o755


def test_data_dir_that_is_a_file(tmp_path: Path) -> None:
    file = tmp_path / "f"
    file.write_text("x")
    with pytest.raises(DataDirError):
        ensure_private_dir(file)


def test_unchangeable_entries_are_collected(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "d"
    root.mkdir()
    (root / "a").write_text("x")
    (root / "b").write_text("x")
    real_chmod = os.chmod

    def fake(path: object, m: int, *args: object, **kw: object) -> None:
        if str(path).endswith(("a", "b")):
            raise PermissionError(1, "Operation not permitted")
        real_chmod(path, m, *args, **kw)  # pyright: ignore[reportArgumentType]

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "chmod", fake)
        with pytest.raises(DataDirError) as info:
            tighten_tree(root)
    assert str(root / "a") in str(info.value)
    assert str(root / "b") in str(info.value)


def test_entry_vanishing_mid_walk_is_tolerated(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    root = tmp_path / "d"
    root.mkdir()
    (root / "gone").write_text("x")
    real_chmod = os.chmod

    def fake(path: object, m: int, *args: object, **kw: object) -> None:
        if str(path).endswith("gone"):
            raise FileNotFoundError(2, "No such file")
        real_chmod(path, m, *args, **kw)  # pyright: ignore[reportArgumentType]

    with monkeypatch.context() as scoped:
        scoped.setattr(os, "chmod", fake)
        tighten_tree(root)
