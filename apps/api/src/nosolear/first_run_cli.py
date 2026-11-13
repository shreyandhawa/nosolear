"""The `nosolear rescore` command: queues a re-score through the API and follows the job."""

import argparse
import sys
from typing import Final, cast

from nosolear.cli_client import ApiClient, CliError, CliTimeout

RESCORE: Final = "rescore"


def register(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    commands.add_parser(
        RESCORE,
        help="re-score stored attempts under the newest scoring config, with no provider calls",
    )


def _job_id(body: object) -> str:
    if isinstance(body, dict):
        value = cast("dict[str, object]", body).get("job_id")
        if isinstance(value, str):
            return value
    raise CliError("The API did not return a job.")


def run(args: argparse.Namespace, client: ApiClient) -> int | None:
    if args.command != RESCORE:
        return None
    job_id = _job_id(client.post_json("/api/rescore"))
    try:
        job = client.follow_job(job_id, out=sys.stdout)
    except CliTimeout:
        print(
            f"job {job_id} did not finish in time; check it with `nosolear job {job_id}`",
            file=sys.stderr,
        )
        return 3
    status = str(job["status"])
    print(f"Re-scoring {status}: job {job_id}")
    return 0 if status == "done" else 1
