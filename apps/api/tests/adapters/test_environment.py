import sys
from pathlib import Path

import pytest

from nosolear.adapters.environment import SystemEnvironment


def test_module_available_uses_find_spec_without_importing():
    env = SystemEnvironment()
    assert env.module_available("json") is True
    assert env.module_available("definitely_not_a_module_xyz") is False
    # `colorsys` ships with the stdlib, is cheap to detect and must stay unimported
    sys.modules.pop("colorsys", None)
    before = len(sys.modules)
    assert env.module_available("colorsys") is True
    assert "colorsys" not in sys.modules
    assert len(sys.modules) == before


def test_module_available_false_for_dotted_name_with_missing_parent():
    assert SystemEnvironment().module_available("no_such_pkg_xyz.sub") is False


def test_executable_available():
    env = SystemEnvironment()
    assert env.executable_available("sh") is True
    assert env.executable_available("definitely-not-a-program-xyz") is False


def test_path_mode(tmp_path: Path):
    f = tmp_path / "f"
    f.write_text("x")
    f.chmod(0o640)
    env = SystemEnvironment()
    assert env.path_mode(f) == 0o640
    assert env.path_mode(tmp_path / "missing") is None


def test_platform_is_a_pair_of_strings():
    system, machine = SystemEnvironment().platform()
    assert system == sys.platform and machine


def test_path_mode_raises_for_a_broken_symlink(tmp_path: Path):
    link = tmp_path / "link"
    link.symlink_to(tmp_path / "nowhere")
    with pytest.raises(OSError):
        SystemEnvironment().path_mode(link)


def test_path_mode_raises_when_a_parent_is_a_file(tmp_path: Path):
    f = tmp_path / "afile"
    f.write_text("x")
    with pytest.raises(OSError):
        SystemEnvironment().path_mode(f / "child")
