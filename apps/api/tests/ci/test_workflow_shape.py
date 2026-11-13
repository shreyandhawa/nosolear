import re

from nosolear.settings import REPO_ROOT

CI = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text()


def _job(name: str) -> str:
    """The text of one top-level job in ci.yml."""
    match = re.search(rf"^  {name}:\n((?:    .*\n|\n)+)", CI, re.MULTILINE)
    assert match, f"job {name} missing"
    return match.group(1)


def test_token_is_read_only() -> None:
    assert re.search(r"^permissions:\n  contents: read$", CI, re.MULTILINE)


def test_runs_weekly_so_new_advisories_are_reported() -> None:
    assert re.search(r"^  schedule:\n    - cron: ['\"]\d+ \d+ \* \* 1['\"]$", CI, re.MULTILINE)


def test_required_check_names_exist() -> None:
    for name in ("hygiene", "api", "web", "contract", "audit"):
        assert re.search(rf"^  {name}:$", CI, re.MULTILINE), name


def test_api_and_audit_gates_follow_their_matrices() -> None:
    for gate in ("api", "audit"):
        matrix = _job(f"{gate}-matrix")
        assert f"name: {gate} (${{{{ matrix.os }}}})" in matrix
        assert "os: [ubuntu-latest, macos-latest]" in matrix
        assert "fail-fast: false" in matrix
        body = _job(gate)
        assert f"needs: {gate}-matrix" in body
        assert "if: always()" in body
        assert f'test "${{{{ needs.{gate}-matrix.result }}}}" = success' in body


def test_audit_matrix_runs_pip_audit_everywhere_and_pnpm_on_ubuntu_only() -> None:
    matrix = _job("audit-matrix")
    assert "pip-audit" in matrix
    pnpm_audit = matrix.split("pnpm audit", 1)[1]
    assert pnpm_audit.startswith(" --audit-level=moderate")
    before = matrix.split("pnpm audit", 1)[0]
    assert "if: ${{ !cancelled() && runner.os == 'Linux' }}" in before.split("pip-audit", 1)[1]
    assert "pnpm audit --audit-level=high" not in CI


def _steps(job: str) -> list[str]:
    return [s for s in re.split(r"^      - ", job, flags=re.MULTILINE)[1:]]


def test_pip_audit_step_has_no_condition_so_it_runs_on_both_legs() -> None:
    (step,) = [s for s in _steps(_job("audit-matrix")) if "pip-audit" in s]
    assert not re.search(r"^\s+if:", step, re.MULTILINE)


def test_pnpm_steps_run_even_if_pip_audit_failed_but_only_on_linux() -> None:
    condition = "if: ${{ !cancelled() && runner.os == 'Linux' }}"
    steps = _steps(_job("audit-matrix"))
    pnpm_steps = [s for s in steps if "pnpm" in s or "setup-node" in s]
    assert any("pnpm audit" in s for s in pnpm_steps)
    assert any("pnpm install" in s for s in pnpm_steps)
    for step in pnpm_steps:
        assert condition in step, step
