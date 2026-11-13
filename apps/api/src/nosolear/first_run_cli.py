"""The `nosolear rescore`, `calibrate`, `baseline`, `onboarding` and `stand-in` commands. They talk
to the running API through the `ApiClient` and follow their jobs."""

import argparse
import sys
from pathlib import Path
from typing import Any, Final, cast

from nosolear.cli_client import ApiClient, CliError, CliTimeout
from nosolear.domain.errors import NosolearError
from nosolear.ports.providers import Synthesizer

RESCORE: Final = "rescore"
CALIBRATE: Final = "calibrate"
CALIBRATE_STEPS: Final = ("start", "status", "skip", "finish")
BASELINE: Final = "baseline"
BASELINE_STEPS: Final = ("start", "status", "complete", "report")
ONBOARDING: Final = "onboarding"
STAND_IN: Final = "stand-in"
STAND_IN_STEPS: Final = ("calibration", "baseline")
DAILY_HINT: Final = "Daily practice arrives in Phase 1."
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
    baseline = commands.add_parser(
        BASELINE, help="the baseline session: record it, then read the ranked report"
    )
    baseline_steps = baseline.add_subparsers(dest="baseline_step", required=True)
    baseline_steps.add_parser("start", help="list the baseline items to record")
    baseline_steps.add_parser("status", help="show how many items are recorded")
    baseline_steps.add_parser("complete", help="complete the baseline and print its report")
    baseline_steps.add_parser("report", help="print the report of the latest completed baseline")
    commands.add_parser(ONBOARDING, help="show the next first-run step and what it needs")
    stand_in = commands.add_parser(
        STAND_IN,
        help="testing aid: upload TTS audio for every unrecorded calibration or baseline item",
    )
    stand_in.add_argument("kind", choices=STAND_IN_STEPS)


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


def run(
    args: argparse.Namespace,
    client: ApiClient,
    *,
    synthesizer: Synthesizer | None = None,
    data_dir: Path | None = None,
) -> int | None:
    if args.command == CALIBRATE:
        return _calibrate(args.calibrate_step, client)
    if args.command == BASELINE:
        return _baseline(args.baseline_step, client)
    if args.command == ONBOARDING:
        return _onboarding(client)
    if args.command == STAND_IN:
        if synthesizer is None or data_dir is None:
            raise CliError("stand-in needs the synthesizer and the data directory")
        return _stand_in(args.kind, client, synthesizer, data_dir)
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


_EN_DASH: Final = "\u2013"


def _baseline(step: str, client: ApiClient) -> int:
    if step == "start":
        body = _dict(client.post_json("/api/baseline"))
        for item in _list(body, "items"):
            print(f"{item['order']:>3}  {item['attempt_id']}  {item['section']}  {item['text']}")
        return 0
    if step == "status":
        body = _dict(client.get_json("/api/baseline"))
        items = _list(body, "items")
        recorded = sum(1 for item in items if item["recorded"] is True)
        print(f"Recorded {recorded} of {len(items)} baseline items.")
        return 0
    if step == "complete":
        return _print_report(_dict(client.post_json("/api/baseline/complete")))
    return _print_report(_dict(client.get_json("/api/baseline/report")))


def _print_report(body: dict[str, Any]) -> int:
    for number, item in enumerate(_list(body, "items"), start=1):
        low = f"{item['ci_low']:.0%}"
        high = f"{item['ci_high']:.0%}"
        suffix = " provisional" if item["provisional"] is True else ""
        print(
            f"{number}. {item['description']}  {item['p_hat']:.0%} ({low}{_EN_DASH}{high})"
            f"  n={item['n_eff']:.0f}{suffix}"
        )
    for score in _list(body, "skill_scores"):
        print(f"{score['skill']}  {score['score']:.0f}")
    for note in cast("list[str]", body.get("notes", [])):
        print(note)
    return 0


def _onboarding(client: ApiClient) -> int:
    body = _dict(client.get_json("/api/onboarding"))
    step = str(body["step"])
    print(f"Next: {step}")
    if step == "readiness":
        for blocker in _list(body, "blockers"):
            fix = blocker.get("fix") or f"{blocker['component']} is {blocker['status']}"
            print(f"  {fix}")
    elif step == "calibration":
        print("  nosolear calibrate start (or nosolear calibrate skip)")
    elif step == "baseline":
        print("  nosolear baseline start")
    elif step == "report":
        print("  nosolear baseline report")
    else:
        print(f"  {DAILY_HINT}")
    return 0


def _stand_in(kind: str, client: ApiClient, synthesizer: Synthesizer, data_dir: Path) -> int:
    """Synthesizes each unrecorded item's stand-in text, uploads it, and follows every job."""
    path = "/api/calibration" if kind == "calibration" else "/api/baseline"
    body = _dict(client.get_json(path))
    pending = [
        (str(item["attempt_id"]), str(item["stand_in_text"]))
        for item in _list(body, "items")
        if item["recorded"] is False
    ]
    job_ids: list[str] = []
    try:
        for attempt_id, text in pending:
            clip = synthesizer.synthesize(text)
            job_ids.append(client.upload_wav(attempt_id, data_dir / clip.path))
    except NosolearError as exc:
        print(f"stand-in stopped: {exc.safe_message}", file=sys.stderr)
        return 2
    for job_id in job_ids:
        try:
            client.follow_job(job_id, out=sys.stdout)
        except CliTimeout:
            print(
                f"job {job_id} did not finish in time; check it with `nosolear job {job_id}`",
                file=sys.stderr,
            )
            return 3
    print(f"Uploaded {len(job_ids)} stand-in recordings")
    return 0
