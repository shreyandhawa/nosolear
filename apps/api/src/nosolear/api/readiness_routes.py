from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import get_readiness_report
from nosolear.api.schemas import ReadinessOut, ReadinessRowOut
from nosolear.domain.readiness import COMPONENT_LABELS, ReadinessReport

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
