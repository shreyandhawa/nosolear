"""The HTTP client every API-backed CLI command uses. It never prints; `cli.py` chooses the output.

Errors carry only an `ErrorOut` message from the API, or one of the generic sentences below.
A response body is never shown otherwise, so provider text and server internals stay out of the
terminal.
"""

import time
from collections.abc import Callable, Iterator, Mapping
from pathlib import Path
from typing import Any, TextIO, cast
from urllib.parse import quote

import httpx

GENERIC_ERROR = "The API returned an unexpected response."
UNREACHABLE = "Could not reach the API. Is `nosolear serve` running on this address?"
TIMED_OUT = "The API did not answer in time."
READ_FAILED = "The recording file could not be read."
TERMINAL = frozenset({"done", "failed"})
UPLOAD_CHUNK = 64 * 1024


class CliError(Exception):
    """A command failed. The message is safe to print as it is."""


class CliTimeout(CliError):
    """`follow_job` waited longer than its limit."""


def progress_line(name: str, state: str, progress: float, message: str | None = None) -> str:
    """`score        running  20%`: the step, its state, and the job's settled share.

    A skipped step also shows its reason: `probe        skipped  40% (not_available)`.
    """
    line = f"{name:<12} {state:<8} {round(progress * 100):>2}%"
    return f"{line} ({message})" if state == "skipped" and message else line


def _error_message(response: httpx.Response) -> str:
    """The message of an `ErrorOut` body (exactly `code` and `message`), else a generic sentence."""
    try:
        body: object = response.json()
    except ValueError:
        return GENERIC_ERROR
    if isinstance(body, dict):
        fields = cast("dict[str, object]", body)
        message = fields.get("message")
        if set(fields) == {"code", "message"} and isinstance(message, str):
            return message
    return GENERIC_ERROR


def _as_dict(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise CliError(GENERIC_ERROR)
    return cast("dict[str, Any]", body)


def _is_number(value: object) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool)


def _as_job(body: object) -> dict[str, Any]:
    """A `JobOut`-shaped body, else the generic error: a 2xx body is not trusted to be a job."""
    job = _as_dict(body)
    steps = job.get("steps")
    if (
        not isinstance(job.get("status"), str)
        or not _is_number(job.get("progress"))
        or not isinstance(steps, list)
    ):
        raise CliError(GENERIC_ERROR)
    for step in cast("list[object]", steps):
        if not isinstance(step, dict):
            raise CliError(GENERIC_ERROR)
        fields = cast("dict[str, object]", step)
        if not isinstance(fields.get("name"), str) or not isinstance(fields.get("state"), str):
            raise CliError(GENERIC_ERROR)
        for optional in ("error_code", "message"):
            if not isinstance(fields.get(optional), str | None):
                raise CliError(GENERIC_ERROR)
    return job


class ApiClient:
    def __init__(self, http: httpx.Client) -> None:
        self._http = http

    def close(self) -> None:
        self._http.close()

    def _send(self, method: str, path: str, **kwargs: Any) -> object:
        try:
            response = self._http.request(method, path, **kwargs)
        except httpx.TimeoutException:
            raise CliError(TIMED_OUT) from None
        except httpx.HTTPError:
            raise CliError(UNREACHABLE) from None
        if not response.is_success:
            raise CliError(_error_message(response))
        try:
            return response.json()
        except ValueError:
            raise CliError(GENERIC_ERROR) from None

    def get_json(self, path: str) -> object:
        return self._send("GET", path)

    def post_json(self, path: str, body: Mapping[str, object] | None = None) -> object:
        return self._send("POST", path, json=body)

    def upload_wav(self, attempt_id: str, path: Path) -> str:
        """Streams the file as the raw `audio/wav` body. Returns the job id."""
        try:
            size = path.stat().st_size
        except OSError:
            raise CliError(READ_FAILED) from None

        def chunks() -> Iterator[bytes]:
            with path.open("rb") as handle:
                while block := handle.read(UPLOAD_CHUNK):
                    yield block

        try:
            body = self._send(
                "POST",
                f"/api/attempts/{quote(attempt_id, safe='')}/recording",
                content=chunks(),
                headers={"Content-Type": "audio/wav", "Content-Length": str(size)},
            )
        except OSError:
            raise CliError(READ_FAILED) from None
        job_id = _as_dict(body).get("job_id")
        if not isinstance(job_id, str):
            raise CliError(GENERIC_ERROR)
        return job_id

    def get_job(self, job_id: str) -> dict[str, Any]:
        return _as_job(self.get_json(f"/api/jobs/{quote(job_id, safe='')}"))

    def resume_job(self, job_id: str) -> dict[str, Any]:
        return _as_job(self.post_json(f"/api/jobs/{quote(job_id, safe='')}/resume"))

    def follow_job(
        self,
        job_id: str,
        *,
        out: TextIO | None = None,
        sleep: Callable[[float], None] = time.sleep,
        timeout_s: float = 600.0,
        interval_s: float = 0.5,
    ) -> dict[str, Any]:
        """Polls until the job is done or failed, then returns its final body.

        One line per step change goes to `out`. The timeout counts the waits between polls.
        """
        seen: dict[str, str] = {}
        waited = 0.0
        while True:
            job = self.get_job(job_id)
            steps: list[dict[str, Any]] = job["steps"]
            for step in steps:
                name, state = str(step["name"]), str(step["state"])
                if state != "pending" and seen.get(name) != state:
                    seen[name] = state
                    if out is not None:
                        print(
                            progress_line(name, state, float(job["progress"]), step.get("message")),
                            file=out,
                        )
            if job["status"] in TERMINAL:
                return job
            if waited >= timeout_s:
                raise CliTimeout("The job did not finish in time.")
            sleep(interval_s)
            waited += interval_s
