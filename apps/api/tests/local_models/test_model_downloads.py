import pytest

from nosolear.adapters.hf_models import ensure_model
from nosolear.adapters.local_env import current_platform
from nosolear.adapters.model_specs import FASTER_WHISPER, MLX_WHISPER, WAV2VEC2_ESPEAK
from nosolear.domain.transcriber_choice import Platform


@pytest.mark.local_models
def test_faster_whisper_snapshot_has_the_files_it_loads():
    path = ensure_model(FASTER_WHISPER)
    assert (path / "model.bin").is_file() and (path / "config.json").is_file()


@pytest.mark.local_models
def test_phone_probe_snapshot_has_the_files_it_loads():
    path = ensure_model(WAV2VEC2_ESPEAK)
    assert (path / "pytorch_model.bin").is_file() and (path / "vocab.json").is_file()


@pytest.mark.local_models
@pytest.mark.skipif(
    current_platform() is not Platform.MACOS_ARM64, reason="mlx needs Apple Silicon"
)
def test_mlx_whisper_snapshot_has_the_files_it_loads():
    path = ensure_model(MLX_WHISPER)
    assert (path / "weights.safetensors").is_file() and (path / "config.json").is_file()
