from nosolear.settings import REPO_ROOT


def read(rel: str) -> str:
    return (REPO_ROOT / rel).read_text(encoding="utf-8")


def test_licence_is_mit_for_shreyan_dhawa_2026():
    text = read("LICENSE")
    assert text.startswith("MIT License")
    assert "Copyright (c) 2026 Shreyan Dhawa" in text
    assert "Permission is hereby granted, free of charge" in text


def test_privacy_names_every_destination_and_no_telemetry():
    text = read("PRIVACY.md")
    for needle in ("Azure Speech", "Anthropic", "Hugging Face", "never audio", "no telemetry"):
        assert needle.lower() in text.lower()


def test_security_states_single_user_machine_and_private_reporting():
    text = read("SECURITY.md").lower()
    assert "single-user machine" in text and "privately" in text
    assert "https://github.com/shreyandhawa/nosolear/security/advisories/new" in text


def test_contributing_covers_the_house_rules():
    text = read("CONTRIBUTING.md").lower()
    for needle in (
        "test first",
        "p<phase>/",
        "squash",
        "no real voices",
        "language pack",
        ".env.example",
    ):
        assert needle in text
