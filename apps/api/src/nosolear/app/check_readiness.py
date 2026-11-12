from pathlib import Path

from nosolear.adapters.content_files import load_pack
from nosolear.domain.packs import PackError
from nosolear.domain.readiness import (
    Caps,
    PackStatus,
    ReadinessInputs,
    ReadinessReport,
    build_readiness,
)
from nosolear.ports.environment import EnvironmentProbe
from nosolear.settings import REPO_ROOT, Settings


def _pack_status(settings: Settings) -> PackStatus:
    try:
        pack = load_pack(settings.packs_dir, settings.pack)
    except PackError as exc:
        return PackStatus(settings.pack, None, 0, (str(exc),))
    return PackStatus(pack.id, pack.name, len(pack.hypotheses), ())


def _mode(env: EnvironmentProbe, path: Path, errors: list[str]) -> int | None:
    try:
        return env.path_mode(path)
    except OSError as exc:
        errors.append(f"cannot inspect {path}: {exc.strerror or type(exc).__name__}")
        return None


def check_readiness(settings: Settings, env: EnvironmentProbe) -> ReadinessReport:
    """Reads settings and probes the machine; writes nothing and never reveals a key."""
    system, machine = env.platform()
    errors: list[str] = []
    data_dir_mode = _mode(env, settings.data_dir, errors)
    env_file_mode = _mode(env, REPO_ROOT / ".env", errors)
    modules = frozenset(
        m
        for m in ("mlx_whisper", "faster_whisper", "torch", "transformers")
        if env.module_available(m)
    )
    return build_readiness(
        ReadinessInputs(
            azure_key_set=settings.azure_speech_key is not None,
            azure_region=settings.azure_speech_region,
            azure_locale=settings.azure_locale,
            anthropic_key_set=settings.anthropic_api_key is not None,
            coach_model=settings.coach_model,
            transcriber=settings.transcriber,
            modules=modules,
            espeak_installed=env.executable_available("espeak-ng"),
            system=system,
            machine=machine,
            pack=_pack_status(settings),
            data_dir=str(settings.data_dir),
            data_dir_mode=data_dir_mode,
            env_file_mode=env_file_mode,
            caps=Caps(
                azure_audio_hours=settings.cap_azure_audio_hours,
                tts_chars=settings.cap_azure_tts_chars,
                claude_tokens=settings.cap_claude_tokens,
            ),
            usage=None,
            capabilities=None,
            inspect_errors=tuple(errors),
        )
    )
