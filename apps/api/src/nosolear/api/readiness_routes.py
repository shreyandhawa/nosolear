from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from sqlalchemy import Engine

from nosolear.api.deps import (
    Services,
    build_capability_probes,
    get_readiness_report,
    get_services,
    get_settings,
)
from nosolear.api.schemas import ProbeOutcomeOut, ProbeRunOut, ReadinessOut, ReadinessRowOut
from nosolear.app.probe_capabilities import probe_capabilities
from nosolear.domain.readiness import COMPONENT_LABELS, ReadinessReport
from nosolear.persistence.capabilities import CapabilityRepository
from nosolear.settings import Settings

router = APIRouter()


def _to_out(report: ReadinessReport) -> ReadinessOut:
    return ReadinessOut(
        ready=report.ready,
        rows=[
            ReadinessRowOut(
                component=r.component.value,
                label=COMPONENT_LABELS[r.component],
                status=r.status.value,
                reason=r.reason,
                fix=r.fix,
            )
            for r in report.rows
        ],
    )


@router.get("/api/readiness", operation_id="getReadiness")
def get_readiness(
    report: Annotated[ReadinessReport, Depends(get_readiness_report)],
) -> ReadinessOut:
    return _to_out(report)


@router.post("/api/readiness/probe", operation_id="runReadinessProbe")
def run_readiness_probe(
    request: Request,
    settings: Annotated[Settings, Depends(get_settings)],
    services: Annotated[Services, Depends(get_services)],
) -> ProbeRunOut:
    """`doctor --probe` from the app: paid calls through the app's metered ports, so POST only.
    Each outcome's message is the safe one its adapter gave."""
    engine = cast(Engine, request.app.state.engine)
    probes = build_capability_probes(
        settings, services.providers, engine=engine, clock=services.clock
    )
    outcomes = probe_capabilities(probes=probes, store=CapabilityRepository(engine))
    return ProbeRunOut(
        outcomes=[ProbeOutcomeOut(adapter=o.adapter, ok=o.ok, message=o.message) for o in outcomes]
    )
