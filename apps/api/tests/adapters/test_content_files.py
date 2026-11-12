import os
from pathlib import Path

import pytest

from nosolear.adapters.content_files import list_pack_ids, load_pack
from nosolear.domain.packs import PackError

VALID = """\
id = "demo"
name = "Demo"
description = "A demo pack."
[[hypotheses]]
key = "sound.sub.v.w"
reason = "one v-w sound"
[calibration]
emphasis = ["sound.sub.v.w"]
"""


def make_pack(root: Path, pack_id: str = "demo", text: str = VALID) -> Path:
    directory = root / pack_id
    directory.mkdir(parents=True)
    (directory / "pack.toml").write_text(text, encoding="utf-8")
    return directory


def test_loads_a_valid_pack(tmp_path: Path):
    make_pack(tmp_path)
    pack = load_pack(tmp_path, "demo")
    assert pack.id == "demo"
    assert pack.hypotheses[0].key == "sound.sub.v.w"


@pytest.mark.parametrize("bad_id", ["../x", "NEPALI", "a/b", ""])
def test_bad_ids_rejected_before_any_file_access(tmp_path: Path, bad_id: str):
    # Something that would otherwise resolve: a sibling pack and a directory one level up.
    make_pack(tmp_path / "packs", "x")
    make_pack(tmp_path, "NEPALI")
    with pytest.raises(PackError) as err:
        load_pack(tmp_path / "packs", bad_id)
    assert "\n" not in str(err.value)


def test_malformed_toml(tmp_path: Path):
    make_pack(tmp_path, text="id = [")
    with pytest.raises(PackError) as err:
        load_pack(tmp_path, "demo")
    assert "\n" not in str(err.value)


def test_missing_directory(tmp_path: Path):
    with pytest.raises(PackError):
        load_pack(tmp_path, "demo")


def test_id_must_match_directory(tmp_path: Path):
    make_pack(tmp_path, "other")
    with pytest.raises(PackError, match="id"):
        load_pack(tmp_path, "other")


def test_oversized_file(tmp_path: Path):
    make_pack(tmp_path, text=VALID + "# " + "x" * 70_000 + "\n")
    with pytest.raises(PackError, match="large"):
        load_pack(tmp_path, "demo")


def test_symlinked_directory_outside_packs_dir(tmp_path: Path):
    outside = make_pack(tmp_path / "elsewhere", "demo")
    packs = tmp_path / "packs"
    packs.mkdir()
    os.symlink(outside, packs / "demo")
    with pytest.raises(PackError) as err:
        load_pack(packs, "demo")
    assert "\n" not in str(err.value)


def test_validation_failure_is_a_pack_error(tmp_path: Path):
    make_pack(tmp_path, text=VALID.replace("sound.sub.v.w", "grammar.artcle", 1))
    with pytest.raises(PackError, match="not a taxonomy key"):
        load_pack(tmp_path, "demo")


def test_list_pack_ids_sorted_and_filtered(tmp_path: Path):
    for name in ("nepali", "neutral", "Bad", "has-dash"):
        (tmp_path / name).mkdir()
    (tmp_path / "file_not_dir").write_text("x")
    assert list_pack_ids(tmp_path) == ("nepali", "neutral")


def test_list_pack_ids_missing_dir(tmp_path: Path):
    assert list_pack_ids(tmp_path / "none") == ()
