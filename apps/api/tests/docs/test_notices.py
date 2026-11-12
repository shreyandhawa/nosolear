import json
import re
import tomllib

import pytest

from nosolear.settings import REPO_ROOT

NOTICES = "THIRD_PARTY_NOTICES"


def read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def _table_names(text: str, marker: str) -> set[str]:
    block = re.search(rf"<!-- {marker}:start -->(.*?)<!-- {marker}:end -->", text, re.DOTALL)
    assert block, f"missing {marker} markers"
    names: set[str] = set()
    for line in block.group(1).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if (
            line.startswith("|")
            and cells[0] not in ("Name", "")
            and not set(cells[0]) <= {"-", ":"}
        ):
            names.add(cells[0])
    return names


def listed_python_names(text: str) -> set[str]:
    return {normalize(n) for n in _table_names(text, "python-dependencies")}


def listed_web_names(text: str) -> set[str]:
    return _table_names(text, "web-dependencies")


def section_for(text: str, component: str) -> str:
    for section in re.split(r"^## ", text, flags=re.MULTILINE)[1:]:
        if component.lower() in section.splitlines()[0].lower():
            return section
    raise AssertionError(f"no section for {component}")


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
    assert re.search(r"Verified: 20\d\d-\d\d-\d\d", section)


def test_crisperwhisper_is_flagged_non_commercial_and_opt_in():
    s = section_for(read(NOTICES), "CrisperWhisper").lower()
    assert "non-commercial" in s and "opt-in" in s and "mit licence does not cover" in s


def test_espeak_is_gpl_separate_executable():
    s = section_for(read(NOTICES), "espeak-ng")
    assert "GPL-3.0" in s and "separate executable" in s and "phonemizer" in s
