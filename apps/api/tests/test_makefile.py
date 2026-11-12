from nosolear.settings import REPO_ROOT


def _recipes() -> dict[str, str]:
    recipes: dict[str, list[str]] = {}
    current = ""
    for line in (REPO_ROOT / "Makefile").read_text().splitlines():
        if line.startswith("\t"):
            recipes.setdefault(current, []).append(line)
        elif ":" in line and not line.startswith((".", " ")):
            current = line.split(":")[0].strip()
    return {k: "\n".join(v) for k, v in recipes.items()}


def test_api_recipes_use_nosolear_serve() -> None:
    recipes = _recipes()
    for name in ("api", "api-dev"):
        assert "nosolear serve" in recipes[name]
        assert "uvicorn" not in recipes[name]


def test_no_recipe_binds_all_interfaces() -> None:
    assert all("0.0.0.0" not in body for body in _recipes().values())
