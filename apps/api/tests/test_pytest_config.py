import pytest


def test_live_marker_is_registered_and_excluded_by_default(pytestconfig: pytest.Config) -> None:
    assert "live" in "\n".join(pytestconfig.getini("markers"))
    addopts = pytestconfig.getini("addopts")
    assert "--strict-markers" in addopts
    assert "not live" in " ".join(addopts)
