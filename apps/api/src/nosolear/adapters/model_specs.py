"""The pinned model snapshots Nosolear loads (ARCHITECTURE.md section 15).

Each spec names a full commit SHA and only the files its loader reads. The SHAs are recorded in
THIRD_PARTY_NOTICES with their licences. A configured model name maps to a spec through a table,
so an unpinned model is never fetched.
"""

from collections.abc import Mapping

from nosolear.adapters.hf_models import ModelSpec
from nosolear.domain.errors import CapabilityMissing

FASTER_WHISPER = ModelSpec(
    label="faster-whisper",
    repo_id="Systran/faster-whisper-small.en",
    revision="d1d751a5f8271d482d14ca55d9e2deeebbae577f",
    allow_patterns=("config.json", "model.bin", "tokenizer.json", "vocabulary.txt"),
)
MLX_WHISPER = ModelSpec(
    label="mlx-whisper",
    repo_id="mlx-community/whisper-large-v3-turbo",
    revision="a4aaeec0636e6fef84abdcbe3544cb2bf7e9f6fb",
    allow_patterns=("config.json", "weights.safetensors"),
)
CRISPER_WHISPER = ModelSpec(
    label="CrisperWhisper",
    repo_id="nyralabs/CrisperWhisper",
    revision="5a513ffabb3429bb61da3521c4e24fbd33ec3e7c",
    allow_patterns=(
        "added_tokens.json",
        "config.json",
        "generation_config.json",
        "merges.txt",
        "model.safetensors",
        "normalizer.json",
        "preprocessor_config.json",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.json",
    ),
    gated=True,
)
WAV2VEC2_ESPEAK = ModelSpec(
    label="phone probe",
    repo_id="facebook/wav2vec2-lv-60-espeak-cv-ft",
    revision="ae45363bf3413b374fecd9dc8bc1df0e24c3b7f4",
    allow_patterns=(
        "config.json",
        "preprocessor_config.json",
        "pytorch_model.bin",
        "special_tokens_map.json",
        "tokenizer_config.json",
        "vocab.json",
    ),
)

FASTER_WHISPER_MODELS: Mapping[str, ModelSpec] = {"small.en": FASTER_WHISPER}
MLX_WHISPER_MODELS: Mapping[str, ModelSpec] = {"whisper-large-v3-turbo": MLX_WHISPER}

ALL_SPECS: tuple[ModelSpec, ...] = (FASTER_WHISPER, MLX_WHISPER, CRISPER_WHISPER, WAV2VEC2_ESPEAK)


def model_spec_for(table: Mapping[str, ModelSpec], value: str) -> ModelSpec:
    """The pinned spec for a configured model name, or `CapabilityMissing` naming the choices."""
    try:
        return table[value]
    except KeyError:
        choices = ", ".join(sorted(table))
        raise CapabilityMissing(f"No pinned model named {value}; choose one of {choices}") from None
