"""The recording upload: a raw `audio/wav` body, streamed to the data dir under a size cap."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from starlette.concurrency import run_in_threadpool

from nosolear.api.deps import Services, get_services
from nosolear.api.errors import ApiError
from nosolear.api.schemas import ErrorOut, UploadAcceptedOut
from nosolear.app.upload_recording import UploadResult, upload_recording
from nosolear.domain.audio import check_declared_length
from nosolear.domain.errors import InvalidAudio
from nosolear.ports.audio import PendingUpload, RecordingExists, UnknownAttempt

router = APIRouter()

WAV_CONTENT_TYPE = "audio/wav"
UNKNOWN_ATTEMPT = "No attempt has this id."
RECORDING_EXISTS = "This attempt already has a recording."

_WAV_BODY = {
    "required": True,
    "content": {WAV_CONTENT_TYPE: {"schema": {"type": "string", "format": "binary"}}},
}


def _media_type(request: Request) -> str:
    """The Content-Type without parameters, lower-cased (`Audio/WAV; rate=16000` is `audio/wav`)."""
    raw = request.headers.get("content-type", "")
    return raw.split(";", 1)[0].strip().lower()


def _commit(
    *,
    attempt_id: str,
    upload: PendingUpload,
    services: Services,
) -> UploadResult:
    try:
        return upload_recording(
            attempt_id=attempt_id,
            upload=upload,
            attempts=services.attempts,
            recordings=services.recordings,
            audio=services.audio_store,
        )
    except UnknownAttempt:
        raise ApiError(404, "unknown_attempt", UNKNOWN_ATTEMPT) from None
    except RecordingExists:
        raise ApiError(409, "recording_exists", RECORDING_EXISTS) from None


@router.post(
    "/api/attempts/{attempt_id}/recording",
    operation_id="uploadRecording",
    status_code=202,
    openapi_extra={"requestBody": _WAV_BODY},
    responses={
        400: {"model": ErrorOut},
        404: {"model": ErrorOut},
        409: {"model": ErrorOut},
        413: {"model": ErrorOut},
        415: {"model": ErrorOut},
    },
)
async def upload_attempt_recording(
    attempt_id: str,
    request: Request,
    services: Annotated[Services, Depends(get_services)],
) -> UploadAcceptedOut:
    if _media_type(request) != WAV_CONTENT_TYPE:
        raise InvalidAudio("bad_content_type")
    exists = await run_in_threadpool(services.attempts.exists, attempt_id)
    if not exists:
        raise ApiError(404, "unknown_attempt", UNKNOWN_ATTEMPT)
    check_declared_length(request.headers.get("content-length"))
    upload = services.audio_store.begin_upload()
    try:
        async for chunk in request.stream():
            upload.write(chunk)
        result = await run_in_threadpool(
            _commit, attempt_id=attempt_id, upload=upload, services=services
        )
    except BaseException:
        upload.abort()
        raise
    services.runner.wake()
    return UploadAcceptedOut(
        recording_id=result.recording_id,
        job_id=result.job_id,
        duration_ms=result.duration_ms,
    )
