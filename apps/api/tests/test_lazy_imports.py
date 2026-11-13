import subprocess
import sys

HEAVY = [
    "torch",
    "transformers",
    "faster_whisper",
    "mlx",
    "mlx_whisper",
    "huggingface_hub",
    "ctranslate2",
]


def test_base_entry_points_import_no_heavy_library():
    code = (
        "import sys, nosolear.api.app, nosolear.api.deps, nosolear.cli; "
        f"print([m for m in {HEAVY!r} if m in sys.modules])"
    )
    out = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, check=True)
    assert out.stdout.strip() == "[]"
