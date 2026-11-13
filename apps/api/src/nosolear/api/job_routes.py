from typing import Annotated

from fastapi import APIRouter, Depends

from nosolear.api.deps import Services, get_job_queue, get_services
from nosolear.api.errors import ApiError
from nosolear.api.schemas import ErrorOut, JobOut, StepOut
from nosolear.domain.jobs import Job
from nosolear.ports.jobs import JobNotResumable, JobQueue, UnknownJob

router = APIRouter()

UNKNOWN_JOB = "No job has this id."
NOT_RESUMABLE = "Only a failed job can be resumed."


def _to_out(job: Job) -> JobOut:
    return JobOut(
        id=job.id,
        kind=job.kind.value,
        attempt_id=job.attempt_id,
        status=job.status.value,
        step=job.step,
        progress=job.progress,
        tries=job.tries,
        steps=[
            StepOut(
                name=s.name,
                state=s.state.value,
                error_code=s.error_code,
                message=s.message,
            )
            for s in job.steps
        ],
    )


@router.get(
    "/api/jobs/{job_id}",
    operation_id="getJob",
    responses={404: {"model": ErrorOut}},
)
def get_job(
    job_id: str,
    jobs: Annotated[JobQueue, Depends(get_job_queue)],
) -> JobOut:
    job = jobs.get(job_id)
    if job is None:
        raise ApiError(404, "unknown_job", UNKNOWN_JOB)
    return _to_out(job)


@router.post(
    "/api/jobs/{job_id}/resume",
    operation_id="resumeJob",
    responses={404: {"model": ErrorOut}, 409: {"model": ErrorOut}},
)
def resume_job(
    job_id: str,
    services: Annotated[Services, Depends(get_services)],
) -> JobOut:
    try:
        job = services.jobs.resume(job_id)
    except UnknownJob:
        raise ApiError(404, "unknown_job", UNKNOWN_JOB) from None
    except JobNotResumable:
        raise ApiError(409, "job_not_resumable", NOT_RESUMABLE) from None
    services.runner.wake()
    return _to_out(job)
