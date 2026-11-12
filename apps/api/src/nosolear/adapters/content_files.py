"""Read language packs and calibration specs from the committed `content/` directory."""

import re
import tomllib
from pathlib import Path

from nosolear.domain.calibration_items import (
    CalibrationSpec,
    parse_calibration_specs,
    validate_calibration_specs,
)
from nosolear.domain.packs import (
    PACK_ID_PATTERN,
    LanguagePack,
    PackError,
    parse_pack,
    validate_pack,
)
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY

MAX_PACK_BYTES = 64 * 1024
MAX_CALIBRATION_BYTES = 256 * 1024
_ID_RE = re.compile(PACK_ID_PATTERN)


def _read_toml(path: Path, limit: int, label: str) -> dict[str, object]:
    try:
        if path.stat().st_size > limit:
            raise PackError(f"{label}: file is too large")
        with path.open("rb") as handle:
            return tomllib.load(handle)
    except tomllib.TOMLDecodeError, UnicodeDecodeError, RecursionError:
        raise PackError(f"{label}: invalid TOML") from None
    except OSError:
        raise PackError(f"{label}: cannot be read") from None


def load_pack(packs_dir: Path, pack_id: str) -> LanguagePack:
    if not _ID_RE.fullmatch(pack_id):
        raise PackError("pack id: must be lowercase letters, digits and underscores")
    label = f"pack {pack_id}"
    try:
        root = packs_dir.resolve()
        pack_file = (packs_dir / pack_id / "pack.toml").resolve()
    except OSError, RuntimeError:
        raise PackError(f"{label}: cannot be resolved") from None
    if pack_file.parent.parent != root:
        raise PackError(f"{label}: path is outside the packs directory")
    pack = parse_pack(_read_toml(pack_file, MAX_PACK_BYTES, label))
    if pack.id != pack_id:
        raise PackError(f"{label}: id must equal the directory name")
    problems = validate_pack(pack, DEFAULT_TAXONOMY)
    if problems:
        raise PackError("; ".join(problems))
    return pack


def list_pack_ids(packs_dir: Path) -> tuple[str, ...]:
    try:
        entries = list(packs_dir.iterdir())
    except OSError:
        return ()
    return tuple(sorted(p.name for p in entries if p.is_dir() and _ID_RE.fullmatch(p.name)))


def load_calibration_specs(path: Path) -> tuple[CalibrationSpec, ...]:
    raw = _read_toml(path, MAX_CALIBRATION_BYTES, "calibration items")
    try:
        specs = parse_calibration_specs(raw)
    except ValueError as err:
        raise PackError(f"calibration items: {err}") from None
    problems = validate_calibration_specs(specs, DEFAULT_TAXONOMY)
    if problems:
        raise PackError("; ".join(problems))
    return specs
