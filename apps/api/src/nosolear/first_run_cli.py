"""The `nosolear rescore` and `nosolear calibrate` commands. Both talk to the running API through
the `ApiClient` and follow their jobs."""

import argparse
import sys
from typing import Any, Final, cast

from nosolear.cli_client import ApiClient, CliError, CliTimeout

RESCORE: Final = "rescore"
CALIBRATE: Final = "calibrate"
CALIBRATE_STEPS: Final = ("start", "status", "skip", "finish")
SKIPPED_MESSAGE: Final = "Calibration skipped. Scores stay provisional until you calibrate."


def register(commands: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:  # pyright: ignore[reportPrivateUsage]
    commands.add_parser(
        RESCORE,
        help="re-score stored attempts under the newest scoring config, with no provider calls",
    )
    calibrate = commands.add_parser(
        CALIBRATE, help="calibrate the detectors on your own voice (section 9.2)"
    )
    steps = calibrate.add_subparsers(dest="calibrate_step", required=True)
    steps.add_parser("start", help="list the calibration takes to record")
    steps.add_parser("status", help="show how many takes are recorded, and the results")
    steps.add_parser("skip", help="skip calibration; scores stay provisional")
    steps.add_parser("finish", help="score the recorded takes and enable the detectors that pass")


def _job_id(body: object) -> str:
    if isinstance(body, dict):
        value = cast("dict[str, object]", body).get("job_id")
        if isinstance(value, str):
            return value
    raise CliError("The API did not return a job.")


def _dict(body: object) -> dict[str, Any]:
    if not isinstance(body, dict):
        raise CliError("The API returned an unexpected response.")
    return cast("dict[str, Any]", body)


def _list(body: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = body.get(key)
    if not isinstance(value, list):
        raise CliError("The API returned an unexpected response.")
    return [
        cast("dict[str, Any]", item)
        for item in cast("list[object]", value)
        if isinstance(item, dict)
    ]


def run(args: argparse.Namespace, client: ApiClient) -> int | None:
    if args.command == CALIBRATE:
        return _calibrate(args.calibrate_step, client)
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


def _calibrate(step: str, client: ApiClient) -> int:
    if step == "start":
        run_body = _dict(client.post_json("/api/calibration"))
        for item in _list(run_body, "items"):
            print(f"{item['order']:>3}  {item['attempt_id']}  {item['instruction']}")
        return 0
    if step == "status":
        run_body = _dict(client.get_json("/api/calibration"))
        items = _list(run_body, "items")
        recorded = sum(1 for item in items if item["recorded"] is True)
        print(f"Recorded {recorded} of {len(items)} calibration takes. Run {run_body['status']}.")
        for result in _list(run_body, "results"):
            verdict = "enabled" if result["enabled"] else "off"
            print(f"{result['detector']:<12} {result['error_key']:<24} {verdict}")
        return 0
    if step == "skip":
        _dict(client.post_json("/api/calibration/skip"))
        print(SKIPPED_MESSAGE)
        return 0
    job_id = _job_id(client.post_json("/api/calibration/finish"))
    try:
        job = client.follow_job(job_id, out=sys.stdout)
    except CliTimeout:
        print(
            f"job {job_id} did not finish in time; check it with `nosolear job {job_id}`",
            file=sys.stderr,
        )
        return 3
    if job["status"] != "done":
        print(f"calibration {job['status']}: job {job_id}")
        return 1
    run_body = _dict(client.get_json("/api/calibration"))
    enabled = [r for r in _list(run_body, "results") if r["enabled"] is True]
    if not enabled:
        print("No detector passed the calibration rule. Scores stay provisional.")
    for result in enabled:
        print(f"enabled  {result['error_key']} via {result['detector']}")
    return 0
