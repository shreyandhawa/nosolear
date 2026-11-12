import re

from nosolear.cli import _parser
from nosolear.settings import REPO_ROOT, Settings

README = (REPO_ROOT / "README.md").read_text()
TICKED = re.findall(r"`([^`\n]+)`", README)
FIELD_NAMES = {f"NOSOLEAR_{f.upper()}" for f in Settings.model_fields}


def _make_targets() -> set[str]:
    targets: set[str] = set()
    for line in (REPO_ROOT / "Makefile").read_text().splitlines():
        if line.startswith(".PHONY:"):
            targets.update(line.removeprefix(".PHONY:").split())
    return targets


def _subcommands() -> set[str]:
    subparsers = next(a for a in _parser()._actions if hasattr(a, "choices") and a.choices)
    return set(subparsers.choices or ())


def test_every_make_target_in_readme_exists() -> None:
    used = set(re.findall(r"\bmake ([a-z][a-z-]*)", README))
    assert {"setup", "api", "web"} <= used
    assert used <= _make_targets()


def test_every_nosolear_subcommand_in_readme_exists() -> None:
    used = set(re.findall(r"\bnosolear ([a-z][a-z-]*)", README))
    assert {"doctor", "serve"} <= used
    assert used <= _subcommands()


def test_every_env_var_in_readme_is_a_setting() -> None:
    used = set(re.findall(r"NOSOLEAR_[A-Z_]+", README))
    assert used
    assert used <= FIELD_NAMES


def test_readme_has_required_sections() -> None:
    for heading in (
        "Platforms",
        "Prerequisites",
        "Get your keys",
        "Set up",
        "Check your setup",
        "Optional extras",
        "What leaves your machine",
        "Costs",
        "Security",
    ):
        assert re.search(rf"^## {re.escape(heading)}$", README, re.M), heading


def test_readme_warns_about_single_user_machines_and_links_licence_files() -> None:
    text = README.lower()
    for needle in ("single-user machine", "third_party_notices", "privacy.md", "security.md"):
        assert needle in text


def test_security_section_states_the_dev_server_rules() -> None:
    section = next(s for s in re.split(r"^## ", README, flags=re.M) if s.startswith("Security\n"))
    for needle in ("single-user machine", "--host", "5173", "8000"):
        assert needle in section, needle
    assert "uvicorn" not in README


def test_readme_no_longer_describes_a_nepali_only_app() -> None:
    assert "native nepali speaker" not in README.lower()
