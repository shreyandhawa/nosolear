"""`GET /api/onboarding`: the next step, the blockers with their fixes, and no side effects."""

from collections.abc import Callable

from factories import count
from harness import Harness

from nosolear.domain.readiness import Component, ReadinessReport, ReadinessRow, ReadinessStatus


def _with_missing(component: Component, status: ReadinessStatus, fix: str) -> ReadinessReport:
    rows = []
    for c in Component:
        if c is component:
            rows.append(ReadinessRow(c, status, "not set", fix))
        else:
            rows.append(ReadinessRow(c, ReadinessStatus.READY, "ok", None))
    return ReadinessReport(rows=tuple(rows))


def test_onboarding_reports_blockers_with_fixes(make_harness: Callable[..., Harness]):
    fix = "set NOSOLEAR_ANTHROPIC_API_KEY in .env"
    h = make_harness(readiness=_with_missing(Component.ANTHROPIC, ReadinessStatus.MISSING, fix))
    body = h.client.get("/api/onboarding").json()
    assert body["step"] == "readiness"
    assert body["blockers"] == [{"component": "anthropic", "status": "missing", "fix": fix}]
    assert body["calibration"] == "not_run"
    assert body["baseline"] == "not_started" and body["baseline_session_id"] is None


def test_onboarding_starts_at_calibration_when_ready(make_harness: Callable[..., Harness]):
    h = make_harness()
    body = h.client.get("/api/onboarding").json()
    assert body["step"] == "calibration" and body["blockers"] == []


def test_onboarding_get_has_no_side_effects(make_harness: Callable[..., Harness]):
    h = make_harness()
    tables = ("sessions", "attempts", "calibration_runs", "jobs", "profile_snapshots")

    def counts() -> dict[str, int]:
        return {table: count(h.engine, table) for table in tables}

    before = counts()
    for _ in range(3):
        assert h.client.get("/api/onboarding").status_code == 200
    assert counts() == before
