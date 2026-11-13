import os
import re

import pytest

from nosolear.adapters.hf_models import ModelSpec, ensure_model
from nosolear.adapters.model_specs import (
    ALL_SPECS,
    CRISPER_WHISPER,
    FASTER_WHISPER,
    FASTER_WHISPER_MODELS,
    MLX_WHISPER,
    MLX_WHISPER_MODELS,
    model_spec_for,
)
from nosolear.domain.errors import CapabilityMissing, ProviderUnavailable

SHA = "0123456789abcdef0123456789abcdef01234567"


def test_revision_must_be_full_sha():
    with pytest.raises(ValueError):
        ModelSpec("x", "org/model", "main", ("*.json",))
    with pytest.raises(ValueError):
        ModelSpec("x", "org/model", SHA[:12], ("*.json",))


def test_repo_id_must_be_owner_and_name():
    with pytest.raises(ValueError):
        ModelSpec("x", "just-a-name", SHA, ("*.json",))


def test_every_pinned_spec_is_a_sha():
    assert all(re.fullmatch(r"[0-9a-f]{40}", s.revision) for s in ALL_SPECS)


def test_ensure_model_pins_revision_and_disables_telemetry(monkeypatch, tmp_path):
    monkeypatch.delenv("HF_HUB_DISABLE_TELEMETRY", raising=False)
    seen = {}

    def download(**kw):
        seen.update(kw, telemetry=os.environ.get("HF_HUB_DISABLE_TELEMETRY"))
        return str(tmp_path)

    assert ensure_model(FASTER_WHISPER, download=download) == tmp_path
    assert seen["revision"] == FASTER_WHISPER.revision and seen["telemetry"] == "1"
    assert seen["repo_id"] == FASTER_WHISPER.repo_id
    assert seen["allow_patterns"] == list(FASTER_WHISPER.allow_patterns)


def test_offline_first_use_is_provider_unavailable():
    def download(**kw):
        raise OSError("connection reset by peer")

    with pytest.raises(ProviderUnavailable, match="Couldn't download the faster-whisper") as info:
        ensure_model(FASTER_WHISPER, download=download)
    assert info.value.__cause__ is None
    assert "connection reset" not in str(info.value)


def test_gated_download_failure_names_the_licence_step():
    def download(**kw):
        raise OSError("401")

    with pytest.raises(ProviderUnavailable, match="hf auth login"):
        ensure_model(CRISPER_WHISPER, download=download)


def test_model_settings_map_to_pinned_specs():
    assert model_spec_for(FASTER_WHISPER_MODELS, "small.en") is FASTER_WHISPER
    assert model_spec_for(MLX_WHISPER_MODELS, "whisper-large-v3-turbo") is MLX_WHISPER
    with pytest.raises(CapabilityMissing, match="No pinned model named nope"):
        model_spec_for(FASTER_WHISPER_MODELS, "nope")
