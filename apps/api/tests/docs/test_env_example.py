import re

from nosolear.settings import REPO_ROOT, Settings

LINES = (REPO_ROOT / ".env.example").read_text().splitlines()
ASSIGNMENT = re.compile(r"^#?\s*(NOSOLEAR_[A-Z0-9_]+)=(.*)$")


def _assignments() -> dict[str, str]:
    return {m[1]: m[2] for line in LINES if (m := ASSIGNMENT.match(line))}


def test_every_setting_is_listed() -> None:
    listed = _assignments()
    missing = [f for f in Settings.model_fields if f"NOSOLEAR_{f.upper()}" not in listed]
    assert not missing


def test_no_key_like_setting_has_a_value() -> None:
    for name, value in _assignments().items():
        if name.endswith("_KEY"):
            assert value.strip() == "", name


def test_no_long_token_after_equals() -> None:
    for name, value in _assignments().items():
        assert not re.search(r"[A-Za-z0-9_-]{24,}", value), name
