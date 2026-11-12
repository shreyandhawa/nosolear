import importlib.util
import json
import re
import tomllib
from datetime import date

import pytest

from nosolear.settings import REPO_ROOT

NOTICES = "THIRD_PARTY_NOTICES"


def read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _table_rows(text: str, marker: str) -> list[list[str]]:
    block = re.search(rf"<!-- {marker}:start -->(.*?)<!-- {marker}:end -->", text, re.DOTALL)
    assert block, f"missing {marker} markers"
    rows: list[list[str]] = []
    for line in block.group(1).splitlines():
        if not line.startswith("|"):
            continue
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if cells[0] != "Name" and not set(cells[0]) <= {"-", ":"}:
            rows.append(cells)
    return rows


def listed_python_names(text: str) -> set[str]:
    return {normalize(r[0]) for r in _table_rows(text, "python-dependencies")}


def listed_web_names(text: str) -> set[str]:
    return {r[0] for r in _table_rows(text, "web-dependencies")}


def section_for(text: str, component: str) -> str:
    sections = [s for s in re.split(r"^## ", text, flags=re.MULTILINE)[1:]]
    matches = [s for s in sections if s.splitlines()[0].strip() == component]
    assert len(matches) == 1, f"{len(matches)} sections headed {component!r}"
    return matches[0]


def load_script():
    spec = importlib.util.spec_from_file_location(
        "third_party_licences", REPO_ROOT / "scripts" / "third_party_licences.py"
    )
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_every_locked_python_package_is_listed():
    locked = {normalize(p["name"]) for p in tomllib.loads(read("apps/api/uv.lock"))["package"]} - {
        "nosolear"
    }
    assert locked <= listed_python_names(read(NOTICES))


def test_every_direct_web_dependency_is_listed():
    pkg = json.loads(read("apps/web/package.json"))
    names = set(pkg.get("dependencies", {})) | set(pkg.get("devDependencies", {}))
    assert names <= listed_web_names(read(NOTICES))


@pytest.mark.parametrize(
    "component", ["CrisperWhisper", "espeak-ng", "wav2vec2-lv-60-espeak-cv-ft", "Whisper"]
)
def test_component_section_has_source_and_verification_date(component: str):
    section = section_for(read(NOTICES), component)
    assert re.search(r"Source: https://", section)
    dates = re.findall(r"Verified: (\d{4}-\d{2}-\d{2})", section)
    assert dates
    for d in dates:
        date.fromisoformat(d)


@pytest.mark.parametrize(
    ("component", "licence"),
    [
        ("CrisperWhisper", "CC BY-NC 4.0"),
        ("wav2vec2-lv-60-espeak-cv-ft", "Apache-2.0"),
        ("Whisper", "MIT"),
    ],
)
def test_component_section_states_the_verified_licence(component: str, licence: str):
    assert licence in section_for(read(NOTICES), component)


def test_section_for_rejects_missing_and_prefix_headings():
    text = "## CrisperWhisper\nx\n## Other\ny\n"
    with pytest.raises(AssertionError):
        section_for(text, "Whisper")
    with pytest.raises(AssertionError):
        section_for("## A\n## A\n", "A")


def test_crisperwhisper_is_flagged_non_commercial_and_opt_in():
    s = section_for(read(NOTICES), "CrisperWhisper").lower()
    assert "non-commercial" in s and "opt-in" in s and "mit licence does not cover" in s


def test_espeak_is_gpl_separate_executable():
    s = section_for(read(NOTICES), "espeak-ng")
    assert "GPL-3.0" in s and "separate executable" in s and "phonemizer" in s


@pytest.mark.parametrize("marker", ["python-dependencies", "web-dependencies"])
def test_committed_tables_have_complete_known_rows(marker: str):
    rows = _table_rows(read(NOTICES), marker)
    assert rows
    for row in rows:
        assert len(row) == 3 and all(row), row
        assert not row[2].startswith("UNKNOWN"), row


ROWS = {
    "python": [("alpha", "1.0", "MIT"), ("beta", "2.0", "Apache-2.0")],
    "web": [("gamma", "3.0", "MIT")],
}


@pytest.fixture
def script(tmp_path, monkeypatch: pytest.MonkeyPatch):
    module = load_script()
    notices = tmp_path / NOTICES
    notices.write_text(
        "# t\n<!-- python-dependencies:start -->\nold\n<!-- python-dependencies:end -->\n"
        "<!-- web-dependencies:start -->\nold\n<!-- web-dependencies:end -->\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(module, "NOTICES", notices)
    monkeypatch.setattr(module, "python_rows", lambda: list(ROWS["python"]))
    monkeypatch.setattr(module, "web_rows", lambda: list(ROWS["web"]))
    return module, notices


def test_rewrite_is_idempotent_and_check_passes_after_it(script):
    module, notices = script
    assert module.main([]) == 0
    first = notices.read_text(encoding="utf-8")
    assert "| alpha | 1.0 | MIT |" in first
    assert module.main([]) == 0
    assert notices.read_text(encoding="utf-8") == first
    assert module.main(["--check"]) == 0


def test_check_does_not_write_and_fails_on_drift(script, capsys: pytest.CaptureFixture[str]):
    module, notices = script
    before = notices.read_text(encoding="utf-8")
    assert module.main(["--check"]) == 1
    assert notices.read_text(encoding="utf-8") == before
    assert "python-dependencies" in capsys.readouterr().err
    module.main([])
    notices.write_text(
        notices.read_text(encoding="utf-8").replace(
            "| alpha | 1.0 | MIT |", "| alpha | 9.9 | MIT |"
        ),
        encoding="utf-8",
    )
    assert module.main(["--check"]) == 1


def test_unknown_flag_is_rejected(script):
    module, _ = script
    with pytest.raises(SystemExit) as exit_info:
        module.main(["--chek"])
    assert exit_info.value.code == 2


@pytest.mark.parametrize("flag", [[], ["--check"]])
def test_unknown_licence_fails_both_modes(script, monkeypatch, flag, capsys):
    module, _ = script
    monkeypatch.setattr(module, "python_rows", lambda: [("alpha", "1.0", module.UNKNOWN)])
    assert module.main(flag) == 2
    assert "alpha" in capsys.readouterr().err


def test_environment_errors_exit_2(script, monkeypatch, capsys):
    module, _ = script

    def boom():
        raise module.ScriptError("pnpm not found")

    monkeypatch.setattr(module, "web_rows", boom)
    assert module.main(["--check"]) == 2
    assert "pnpm not found" in capsys.readouterr().err


def test_replace_block_raises_on_missing_markers():
    module = load_script()
    with pytest.raises(module.ScriptError):
        module.replace_block("no markers here", "python-dependencies", "x")


def test_web_rows_wraps_pnpm_failures(monkeypatch: pytest.MonkeyPatch):
    module = load_script()

    def missing(*_a, **_k):
        raise FileNotFoundError

    monkeypatch.setattr(module.subprocess, "run", missing)
    with pytest.raises(module.ScriptError, match="pnpm not found"):
        module.web_rows()

    class Out:
        stdout = "{}"

    monkeypatch.setattr(module.subprocess, "run", lambda *_a, **_k: Out())
    with pytest.raises(module.ScriptError, match="no packages"):
        module.web_rows()

    Out.stdout = "not json"
    with pytest.raises(module.ScriptError, match="parse"):
        module.web_rows()

    Out.stdout = json.dumps({"MIT": [{"name": "only-one", "versions": ["1"]}]})
    with pytest.raises(module.ScriptError, match="direct dependencies"):
        module.web_rows()
