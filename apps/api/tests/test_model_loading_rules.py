"""Static rules for loading models (ARCHITECTURE.md section 15), checked over `src/` with AST."""

import ast
from pathlib import Path

from nosolear.settings import REPO_ROOT

SRC = REPO_ROOT / "apps" / "api" / "src" / "nosolear"
DOWNLOADERS = frozenset({"snapshot_download", "hf_hub_download"})
DOWNLOAD_HOME = "adapters/hf_models.py"


def _called_name(call: ast.Call) -> str | None:
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def violations(root: Path) -> list[str]:
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            name = _called_name(node)
            if any(kw.arg == "trust_remote_code" for kw in node.keywords):
                found.append(f"{rel}:{node.lineno} passes trust_remote_code")
            if name == "from_pretrained" and node.args:
                first = node.args[0]
                if isinstance(first, ast.Constant) and isinstance(first.value, str):
                    found.append(f"{rel}:{node.lineno} loads a repo id, not a pinned snapshot")
            if name in DOWNLOADERS and rel != DOWNLOAD_HOME:
                found.append(f"{rel}:{node.lineno} downloads outside {DOWNLOAD_HOME}")
    return found


def test_no_model_loading_rule_is_broken_in_src():
    assert violations(SRC) == []


def test_the_rules_have_teeth(tmp_path: Path):
    package = tmp_path / "nosolear"
    (package / "adapters").mkdir(parents=True)
    (package / "adapters" / "hf_models.py").write_text(
        "def fetch():\n    return snapshot_download(repo_id='a/b')\n", encoding="utf-8"
    )
    (package / "adapters" / "bad.py").write_text(
        "def load():\n"
        "    Model.from_pretrained('org/model')\n"
        "    Model.from_pretrained(local, trust_remote_code=True)\n"
        "    hf_hub_download(repo_id='a/b')\n",
        encoding="utf-8",
    )
    found = violations(package)
    assert len(found) == 3
    assert all(item.startswith("adapters/bad.py") for item in found)
