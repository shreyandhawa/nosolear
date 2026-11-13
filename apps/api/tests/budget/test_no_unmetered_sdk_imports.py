"""Only raw adapter modules may import a provider SDK; every other import would skip the ledger."""

import ast
from pathlib import Path

from nosolear.settings import REPO_ROOT

SRC = REPO_ROOT / "apps" / "api" / "src" / "nosolear"

SDK_MODULES = frozenset(
    {
        "azure",
        "anthropic",
        "faster_whisper",
        "mlx_whisper",
        "mlx",
        "torch",
        "transformers",
        "huggingface_hub",
        "parselmouth",
    }
)

# Phase 0d turns this into a module -> allowed-SDKs mapping and adds a lazy-import rule.
RAW_ADAPTER_MODULES: frozenset[str] = frozenset()


def sdk_importers(root: Path) -> list[str]:
    """Posix paths (relative to `root`) of every module under `root` that imports an SDK."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: list[str] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names += [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.append(node.module)
        if any(name.split(".")[0] in SDK_MODULES for name in names):
            found.append(path.relative_to(root).as_posix())
    return found


def test_only_raw_adapter_modules_import_an_sdk():
    offenders = [p for p in sdk_importers(SRC) if p not in RAW_ADAPTER_MODULES]
    assert offenders == [], f"SDK imported outside a raw adapter: {offenders}"


def test_scanner_flags_a_planted_offender(tmp_path: Path):
    package = tmp_path / "nosolear"
    (package / "app").mkdir(parents=True)
    (package / "app" / "sneaky.py").write_text(
        "def run():\n    from azure.cognitiveservices import speech\n    return speech\n",
        encoding="utf-8",
    )
    (package / "app" / "fine.py").write_text("import json\n", encoding="utf-8")
    assert sdk_importers(package) == ["app/sneaky.py"]
