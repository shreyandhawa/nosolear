import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[4]
SCRIPT = REPO_ROOT / "scripts" / "check-no-personal-data.sh"

AUDIO = ["wav", "webm", "ogg", "m4a", "mp3", "flac", "aiff", "aif", "caf", "aac", "opus"]
AUDIO += ["mp4", "m4b", "amr", "3gp"]
DB_BASES = ["x.sqlite", "x.sqlite3", "x.db"]
DB_SUFFIXES = ["", "-wal", "-shm", "-journal"]
BLOCKED = [
    "data/nosolear.sqlite",
    "apps/api/data/x.txt",
    "x/take.WAV",
    *[f"a.{ext}" for ext in AUDIO],
    *[f"x/{ext_name}.{ext.upper()}" for ext_name in ["take"] for ext in AUDIO],
    *[f"apps/api/{base}{suffix}" for base in DB_BASES for suffix in DB_SUFFIXES],
    "nosolear.SQLITE-WAL",
]


def run(paths: list[str]) -> int:
    return subprocess.run(["bash", str(SCRIPT)], input="\n".join(paths), text=True).returncode


def test_allows_code_and_docs():
    assert run(["apps/api/src/nosolear/settings.py", "docs/plan-sketch.png", "README.md"]) == 0


def test_allows_names_that_only_look_similar():
    assert run(["apps/api/src/metadata/x.py", "docs/database.md", "src/mydata/x.py"]) == 0


def test_allows_empty_input():
    assert run([]) == 0


@pytest.mark.parametrize("path", BLOCKED)
def test_blocks_personal_data(path: str) -> None:
    assert run([path]) == 1


# gitignore matching is case-sensitive; the hook (grep -i) covers the upper-case variants.
@pytest.mark.parametrize("path", [p for p in BLOCKED if p == p.lower()])
def test_gitignore_covers_personal_data(path: str) -> None:
    ignored = subprocess.run(
        ["git", "check-ignore", "-q", "--no-index", path], cwd=REPO_ROOT, check=False
    )
    assert ignored.returncode == 0, path
