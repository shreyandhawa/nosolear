import os
from pathlib import Path

import pytest

from nosolear.adapters.content_files import list_pack_ids, load_calibration_specs, load_pack
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


def test_symlinked_pack_file_outside_packs_dir(tmp_path: Path):
    outside = make_pack(tmp_path / "elsewhere", "demo") / "pack.toml"
    packs = tmp_path / "packs"
    (packs / "demo").mkdir(parents=True)
    os.symlink(outside, packs / "demo" / "pack.toml")
    with pytest.raises(PackError) as err:
        load_pack(packs, "demo")
    assert "\n" not in str(err.value)


CALIBRATION = """\
[[specs]]
error_key = "sound.sub.v.w"
description = "W instead of V"
words = [["vest", "west"]]
"""

# Bad bytes for both file kinds: not UTF-8, nesting deep enough to exhaust the parser's
# recursion, and an integer too big for a float.
NESTED = "x = " + "[" * 20_000 + "]" * 20_000 + "\n"


def _pack_file(tmp_path: Path, data: bytes) -> object:
    directory = tmp_path / "demo"
    directory.mkdir()
    (directory / "pack.toml").write_bytes(data)
    return lambda: load_pack(tmp_path, "demo")


def _calibration_file(tmp_path: Path, data: bytes) -> object:
    path = tmp_path / "items.toml"
    path.write_bytes(data)
    return lambda: load_calibration_specs(path)


LOADERS = [_pack_file, _calibration_file]
HUGE = b"1" + b"0" * 400


@pytest.mark.parametrize("loader", LOADERS)
@pytest.mark.parametrize(
    "data",
    [
        VALID.encode() + b"# \xff\xfe\n",
        NESTED.encode(),
        b"id = [",
    ],
    ids=["not_utf8", "deeply_nested", "malformed"],
)
def test_unreadable_toml_is_a_one_line_pack_error(tmp_path: Path, loader, data: bytes):
    call = loader(tmp_path, data)
    with pytest.raises(PackError) as err:
        call()  # type: ignore[operator]
    message = str(err.value)
    assert "\n" not in message and "invalid TOML" in message
    assert "0x" not in message and "position" not in message


def test_huge_integer_prior_is_a_pack_error(tmp_path: Path):
    text = VALID.replace("[[hypotheses]]", f"[default_prior]\na0 = {HUGE.decode()}\n[[hypotheses]]")
    make_pack(tmp_path, text=text)
    with pytest.raises(PackError, match=r"default_prior\.a0"):
        load_pack(tmp_path, "demo")


def test_calibration_oversized_file(tmp_path: Path):
    path = tmp_path / "items.toml"
    path.write_text(CALIBRATION + "# " + "x" * 300_000 + "\n", encoding="utf-8")
    with pytest.raises(PackError, match="large"):
        load_calibration_specs(path)


def test_calibration_missing_file(tmp_path: Path):
    with pytest.raises(PackError):
        load_calibration_specs(tmp_path / "nope.toml")


def test_calibration_unknown_key_is_a_pack_error(tmp_path: Path):
    path = tmp_path / "items.toml"
    path.write_text(CALIBRATION.replace("sound.sub.v.w", "grammar.artcle"), encoding="utf-8")
    with pytest.raises(PackError, match="error_key"):
        load_calibration_specs(path)


def test_calibration_wrong_structure_is_a_pack_error(tmp_path: Path):
    path = tmp_path / "items.toml"
    path.write_text('specs = "no"\n', encoding="utf-8")
    with pytest.raises(PackError, match="specs"):
        load_calibration_specs(path)


@pytest.mark.parametrize("loader", LOADERS)
def test_integer_beyond_python_digit_limit_is_a_pack_error(tmp_path: Path, loader):
    call = loader(tmp_path, b"a0 = " + b"1" * 5000 + b"\n")
    with pytest.raises(PackError) as err:
        call()  # type: ignore[operator]
    assert "\n" not in str(err.value) and "invalid TOML" in str(err.value)
