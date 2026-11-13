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

# The raw adapters that may import an SDK (ARCHITECTURE.md section 11). Each one imports its SDK
# only inside a function body; `anthropic` is pure Python and may be imported at module level.
RAW_ADAPTER_MODULES: frozenset[str] = frozenset(
    {
        "adapters/azure_speech.py",
        # The local-model layer (ARCHITECTURE.md section 15): huggingface_hub, torch device checks
        "adapters/hf_models.py",
        "adapters/local_env.py",
    }
)
EAGER_OK = frozenset({"anthropic"})


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


def eager_sdk_importers(root: Path) -> list[str]:
    """Posix paths of modules that import an SDK (other than `EAGER_OK`) at module level."""
    found: list[str] = []
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in tree.body:
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module]
            else:
                continue
            roots = {name.split(".")[0] for name in names}
            if roots & SDK_MODULES and not roots <= EAGER_OK:
                found.append(path.relative_to(root).as_posix())
                break
    return found


def test_sdk_is_imported_only_inside_function_bodies():
    assert eager_sdk_importers(SRC) == []


def test_the_lazy_check_has_teeth(tmp_path: Path):
    package = tmp_path / "nosolear"
    (package / "adapters").mkdir(parents=True)
    (package / "adapters" / "eager.py").write_text(
        "import azure.cognitiveservices.speech as speechsdk\n", encoding="utf-8"
    )
    (package / "adapters" / "lazy.py").write_text(
        "def load():\n    import azure.cognitiveservices.speech\n", encoding="utf-8"
    )
    (package / "adapters" / "anthropic_ok.py").write_text("import anthropic\n", encoding="utf-8")
    assert eager_sdk_importers(package) == ["adapters/eager.py"]
