import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[4] / "scripts" / "check-no-personal-data.sh"


def run(paths: list[str]) -> int:
    return subprocess.run(["bash", str(SCRIPT)], input="\n".join(paths), text=True).returncode


def test_allows_code_and_docs():
    assert run(["apps/api/src/nosolear/settings.py", "docs/plan-sketch.png", "README.md"]) == 0


def test_blocks_audio_and_data_dir():
    for bad in [
        "data/nosolear.sqlite",
        "x/take.WAV",
        "a.webm",
        "b.m4a",
        "c.mp3",
        "d.ogg",
        "e.flac",
    ]:
        assert run([bad]) == 1, bad
