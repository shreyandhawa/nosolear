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

# Which SDK each raw adapter module may import (ARCHITECTURE.md section 11 and the Phase 0d
# global constraints). An SDK is imported only inside a function body, except `anthropic`, which
# is pure Python and may be imported at module level.
ALLOWED: dict[str, set[str]] = {
    "adapters/azure_speech.py": {"azure.cognitiveservices.speech"},
    "adapters/claude_coach.py": {"anthropic"},
    "adapters/hf_models.py": {"huggingface_hub"},
    "adapters/local_env.py": {"torch"},
    "adapters/faster_whisper.py": {"faster_whisper"},
    "adapters/mlx_whisper.py": {"mlx_whisper"},
    "adapters/crisper_whisper.py": {"transformers", "torch"},
    "adapters/wav2vec2_espeak.py": {"transformers", "torch", "numpy"},
}
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
    offenders = [p for p in sdk_importers(SRC) if p not in ALLOWED]
    assert offenders == [], f"SDK imported outside a raw adapter: {offenders}"


def sdk_roots_by_module(root: Path) -> dict[str, set[str]]:
    """Each module under `root` that imports an SDK, with the SDK package names it imports."""
    found: dict[str, set[str]] = {}
    for path in sorted(root.rglob("*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        names: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                names.update(alias.name.split(".")[0] for alias in node.names)
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
        sdks = names & SDK_MODULES
        if sdks:
            found[path.relative_to(root).as_posix()] = sdks
    return found


def test_each_raw_adapter_imports_only_the_sdk_the_table_allows():
    for module, sdks in sdk_roots_by_module(SRC).items():
        allowed = {name.split(".")[0] for name in ALLOWED.get(module, set())}
        assert sdks <= allowed, f"{module} imports {sorted(sdks - allowed)}, not in the table"


def test_the_table_only_lists_modules_that_exist():
    missing = [module for module in ALLOWED if not (SRC / module).is_file()]
    assert missing == []


def test_the_table_check_has_teeth(tmp_path: Path):
    package = tmp_path / "nosolear"
    (package / "adapters").mkdir(parents=True)
    (package / "adapters" / "claude_coach.py").write_text(
        "import anthropic\nimport torch\n", encoding="utf-8"
    )
    found = sdk_roots_by_module(package)
    assert found == {"adapters/claude_coach.py": {"anthropic", "torch"}}
    allowed = {name.split(".")[0] for name in ALLOWED["adapters/claude_coach.py"]}
    assert found["adapters/claude_coach.py"] - allowed == {"torch"}


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
