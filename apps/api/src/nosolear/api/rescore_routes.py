"""`POST /api/rescore`: queues a re-score job. It reads stored analyses and calls no provider."""

from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import Services, get_services
from nosolear.api.schemas import JobAcceptedOut
from nosolear.domain.jobs import JobKind

router = APIRouter()


@router.post(
    "/api/rescore",
    operation_id="startRescore",
    status_code=202,
)
def start_rescore(
    services: Annotated[Services, Depends(get_services)],
) -> JobAcceptedOut:
    job = services.jobs.enqueue(JobKind.RESCORE, None)
    services.runner.wake()
    return JobAcceptedOut(job_id=job.id)
