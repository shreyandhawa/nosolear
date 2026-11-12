import re
from typing import get_args

import pytest

from nosolear.settings import MIN_KEY_LENGTH, REPO_ROOT, Settings

LINES = (REPO_ROOT / ".env.example").read_text().splitlines()
ASSIGNMENT = re.compile(r"^#?\s*(NOSOLEAR_[A-Z0-9_]+)=(.*)$")
FIELD_NAMES = {f"NOSOLEAR_{f.upper()}": f for f in Settings.model_fields}
SECRET_NAMES = {
    f"NOSOLEAR_{f.upper()}"
    for f, info in Settings.model_fields.items()
    if "SecretStr" in repr(info.annotation) or "SecretStr" in repr(get_args(info.annotation))
}


def _assignments() -> dict[str, str]:
    return {m[1]: m[2].strip() for line in LINES if (m := ASSIGNMENT.match(line))}


def _default_text(field: str) -> str:
    default = Settings.model_fields[field].default
    if isinstance(default, tuple):
        return ",".join(default)
    return "" if default is None else str(default)


def test_secret_fields_are_detected() -> None:
    assert sorted(SECRET_NAMES) == ["NOSOLEAR_ANTHROPIC_API_KEY", "NOSOLEAR_AZURE_SPEECH_KEY"]


def test_every_setting_is_listed() -> None:
    listed = _assignments()
    assert not [n for n in FIELD_NAMES if n not in listed]


def test_every_listed_name_is_a_setting() -> None:
    assert not [n for n in _assignments() if n not in FIELD_NAMES]


def test_secret_settings_have_no_value() -> None:
    listed = _assignments()
    for name in SECRET_NAMES:
        assert listed[name] == "", name


def test_documented_defaults_match_the_code() -> None:
    for name, value in _assignments().items():
        if value and FIELD_NAMES[name] != "timezone":
            assert value == _default_text(FIELD_NAMES[name]), name


def test_loading_every_line_as_env_gives_the_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from factories import make_settings

    baseline = make_settings().model_dump()
    for name, value in _assignments().items():
        monkeypatch.setenv(name, value)
    assert make_settings().model_dump() == baseline


def test_no_key_length_token_after_an_equals_sign() -> None:
    documented = {_default_text(f) for f in Settings.model_fields} - {""}
    for line in LINES:
        if "=" not in line:
            continue
        value = line.split("=", 1)[1]
        for known in sorted(documented, key=len, reverse=True):
            value = value.replace(known, "")
        assert not re.search(rf"[A-Za-z0-9_-]{{{MIN_KEY_LENGTH},}}", value), line
