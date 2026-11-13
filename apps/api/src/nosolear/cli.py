"""Command-line entry point and composition root for the `nosolear` command."""

import argparse
import json
import logging
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any, cast
from urllib.parse import quote

import httpx
from pydantic import ValidationError
from sqlalchemy import Engine

from nosolear import first_run_cli
from nosolear.adapters.private_fs import DataDirError
from nosolear.adapters.system_clock import SystemClock
from nosolear.api.deps import (
    build_capability_probes,
    build_ledger,
    build_providers,
    build_stand_in_synthesizer,
    get_environment,
    load_active_pack,
    read_capabilities,
    read_usage,
)
from nosolear.app.check_readiness import check_readiness
from nosolear.app.probe_capabilities import probe_capabilities
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.cli_client import (
    GENERIC_ERROR,
    TERMINAL,
    ApiClient,
    CliError,
    CliTimeout,
    progress_line,
)
from nosolear.dev.seed import seed_observations
from nosolear.domain.capabilities import real_time_factors
from nosolear.domain.errors import NosolearError
from nosolear.domain.packs import LanguagePack, PackError
from nosolear.domain.readiness import format_readiness
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.capabilities import CapabilityRepository
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import (
    AttemptRepository,
    ObservationRepository,
    ProfileRepository,
)
from nosolear.ports.providers import Synthesizer
from nosolear.settings import REPO_ROOT, Settings, settings_error_summary
from nosolear.startup import prepare_process

API_TIMEOUT_S = 30.0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nosolear")
    commands = parser.add_subparsers(dest="command", required=True)
    first_run_cli.register(commands)
    db = commands.add_parser("db", help="database maintenance")
    db_commands = db.add_subparsers(dest="db_command", required=True)
    db_commands.add_parser("upgrade", help="apply migrations")
    commands.add_parser("rebuild-profile", help="recompute and snapshot the profile")
    seed = commands.add_parser("dev-seed", help="append synthetic observations, then rebuild")
    seed.add_argument("--days", type=int, default=14)
    seed.add_argument("--seed", type=int, default=7)
    seed.add_argument("--force", action="store_true", help="append even if observations exist")
    doctor = commands.add_parser("doctor", help="show what is configured and what is missing")
    doctor.add_argument("--probe", action="store_true", help="check live providers (Phase 0d)")
    serve = commands.add_parser("serve", help="run the API on loopback")
    serve.add_argument("--reload", action="store_true", help="restart on code changes (dev)")
    upload = commands.add_parser("upload", help="upload a WAV recording and follow its job")
    upload.add_argument("file", help="a 16-bit mono PCM WAV, at most 120 seconds")
    target = upload.add_mutually_exclusive_group(required=True)
    target.add_argument("--attempt-id", help="the attempt the recording belongs to")
    target.add_argument(
        "--new-attempt",
        action="store_true",
        help="create a daily attempt in the database first (never in the real data directory)",
    )
    upload.add_argument("--no-follow", action="store_true", help="print the job id and exit")
    upload.add_argument("--base-url", help="the API address (default: from the settings)")
    job = commands.add_parser("job", help="show a job, or resume it and follow it")
    job.add_argument("job_id")
    job.add_argument("--resume", action="store_true", help="resume a failed job first")
    job.add_argument("--follow", action="store_true", help="wait until the job is done or failed")
    job.add_argument("--base-url", help="the API address (default: from the settings)")
    plan = commands.add_parser("plan", help="today's daily plan, built once per local day")
    plan.add_argument("--json", action="store_true", help="print the response body")
    plan.add_argument("--base-url", help="the API address (default: from the settings)")
    daily = commands.add_parser("daily", help="today's daily session")
    daily_commands = daily.add_subparsers(dest="daily_command", required=True)
    daily_start = daily_commands.add_parser("start", help="start today's session and its attempt")
    daily_start.add_argument("--base-url", help="the API address (default: from the settings)")
    daily_feedback = daily_commands.add_parser("feedback", help="a daily session's feedback cards")
    daily_feedback.add_argument("session_id", help="the session printed by `daily start`")
    daily_feedback.add_argument(
        "--generate",
        action="store_true",
        help="make or upgrade the cards (the coach is called only for cards it has not written)",
    )
    daily_feedback.add_argument("--base-url", help="the API address (default: from the settings)")
    daily_complete = daily_commands.add_parser("complete", help="close a daily session once")
    daily_complete.add_argument("session_id", help="the session printed by `daily start`")
    daily_complete.add_argument("--base-url", help="the API address (default: from the settings)")
    daily_run = daily_commands.add_parser(
        "run", help="start, upload a WAV, follow the job, print the feedback, then complete"
    )
    daily_run.add_argument("wav", help="a 16-bit mono PCM WAV recording of the prompt")
    daily_run.add_argument(
        "--no-generate",
        action="store_true",
        help="print the stored feedback only (no coach call); it must have been generated",
    )
    daily_run.add_argument("--base-url", help="the API address (default: from the settings)")
    return parser


def _rebuild(engine: Engine, pack: LanguagePack) -> None:
    profile = rebuild_profile(
        observations=ObservationRepository(engine),
        profiles=ProfileRepository(engine, DEFAULT_TAXONOMY),
        taxonomy=DEFAULT_TAXONOMY,
        pack=pack,
        clock=SystemClock(),
    )
    print(f"Rebuilt profile: {len(profile.entries)} keys as of {profile.as_of.isoformat()}")


def _create_attempt(settings: Settings) -> str:
    """A daily attempt in the configured database, which is never the real data directory."""
    engine = create_engine_for(settings.database_url)
    try:
        upgrade_to_head(engine)
        return AttemptRepository(engine).create_attempt(
            session_kind="daily",
            step="speak",
            reference_text=None,
            scripted=False,
            now=SystemClock().now(),
        )
    finally:
        engine.dispose()


def _finish(job_id: str, job: dict[str, Any]) -> int:
    """Prints a terminal job's outcome: 0 for done, 1 for failed (one line per failed step)."""
    if job["status"] == "done":
        print(f"job {job_id} done")
        return 0
    steps = _steps(job)
    failed = [step for step in steps if step["state"] == "failed"]
    for step in failed:
        code = step.get("error_code") or "error"
        message = step.get("message")
        suffix = f" ({message})" if message else ""
        print(f"job {job_id} failed: {step['name']}: {code}{suffix}")
    if not failed:
        print(f"job {job_id} failed")
    return 1


def _steps(job: dict[str, Any]) -> list[dict[str, Any]]:
    return [step for step in job["steps"] if isinstance(step, dict)]


def _follow(api: ApiClient, job_id: str) -> int:
    try:
        job = api.follow_job(job_id, out=sys.stdout)
    except CliTimeout:
        print(
            f"job {job_id} did not finish in time; check it with `nosolear job {job_id}`",
            file=sys.stderr,
        )
        return 3
    return _finish(job_id, job)


def _upload(args: argparse.Namespace, api: ApiClient, attempt_id: str | None) -> int:
    if attempt_id is None:
        print("upload needs --attempt-id or --new-attempt", file=sys.stderr)
        return 2
    path = Path(args.file)
    try:
        job_id = api.upload_wav(attempt_id, path)
    except CliError as exc:
        print(f"upload failed: {exc}", file=sys.stderr)
        return 2
    if args.no_follow:
        print(f"job {job_id} queued")
        return 0
    return _follow(api, job_id)


def _record(body: object, *keys: str) -> dict[str, Any]:
    """A 2xx body is trusted only as far as the keys this command prints."""
    if not isinstance(body, dict) or any(key not in body for key in keys):
        raise CliError(GENERIC_ERROR)
    return cast(dict[str, Any], body)


def _printable(text: str) -> str:
    """Prompt text may come from the coach: control and bidi characters never reach the terminal."""
    return "".join(ch for ch in text if ch.isprintable())


def _focus_line(focus: dict[str, Any]) -> str:
    percent = round(float(focus["p_hat"]) * 100)
    note = ", provisional" if focus["provisional"] else ""
    return f"{focus['skill']}: {focus['error_key']} ({focus['status']}, {percent}%{note})"


def _plan_lines(body: object) -> list[str]:
    plan = _record(body, "foci", "probe", "prompt", "steps")
    lines = [_focus_line(f) for f in plan["foci"]]
    probe = plan["probe"]
    if probe is None:
        lines.append("probe: none")
    else:
        lines.append(f"probe: {probe['skill']}: {probe['error_key']} (due {probe['due_at']})")
    prompt = plan["prompt"]
    lines.append("prompt: none" if prompt is None else f"prompt: {_printable(prompt['text'])}")
    lines.append("steps:")
    for step in plan["steps"]:
        parts = [str(step["kind"])]
        if step["skill"]:
            parts.append(str(step["skill"]))
        if step["duration_s"]:
            parts.append(f"{step['duration_s']}s")
        lines.append("  " + " ".join(parts))
    return lines


def _daily_start_lines(body: object) -> list[str]:
    session = _record(body, "session_id", "attempts")
    attempts: object = session["attempts"]
    if not isinstance(attempts, list) or not attempts:
        raise CliError(GENERIC_ERROR)
    first = _record(cast(list[object], attempts)[0], "id", "prompt_text")
    prompt = first["prompt_text"]
    prompt_line = "prompt: none" if prompt is None else f"prompt: {_printable(str(prompt))}"
    return [f"session {session['session_id']}", f"attempt {first['id']}", prompt_line]


def _daily_start(api: ApiClient) -> int:
    for line in _daily_start_lines(api.post_json("/api/plan/today/session")):
        print(line)
    return 0


def _feedback_lines(body: object) -> list[str]:
    """One card per skill: the fix with its text (and a template's reason), or clean, or not
    scored today. Coach text is printed with control and bidi characters removed."""
    feedback = _record(body, "skills")
    skills = feedback["skills"]
    if not isinstance(skills, list):
        raise CliError(GENERIC_ERROR)
    lines: list[str] = []
    for raw_card in cast(list[object], skills):
        card = _record(raw_card, "skill", "state", "item")
        skill = str(card["skill"])
        if card["state"] == "clean":
            lines.append(f"{skill}: clean")
            continue
        if card["state"] == "not_scored":
            lines.append(f"{skill}: not scored today")
            continue
        if card["item"] is None:
            lines.append(f"{skill}: no card stored")
            continue
        item = _record(
            card["item"], "error_key", "message", "model_text", "source", "fallback_reason"
        )
        tag = f" [template: {item['fallback_reason']}]" if item["source"] == "template" else ""
        lines.append(f"{skill}: {item['error_key']}{tag}")
        lines.append(f"  {_printable(str(item['message']))}")
        if item["model_text"] is not None:
            lines.append(f"  say: {_printable(str(item['model_text']))}")
    return lines


def _session_path(session_id: str, suffix: str) -> str:
    return f"/api/sessions/{quote(session_id, safe='')}/{suffix}"


def _daily_feedback(args: argparse.Namespace, api: ApiClient) -> int:
    path = _session_path(args.session_id, "feedback")
    body = api.post_json(path) if args.generate else api.get_json(path)
    for line in _feedback_lines(body):
        print(line)
    return 0


def _complete(api: ApiClient, session_id: str) -> int:
    done = _record(
        api.post_json(_session_path(session_id, "complete")),
        "session_id",
        "completed_at",
        "already_completed",
    )
    state = "was already completed" if done["already_completed"] else "completed"
    print(f"session {done['session_id']} {state} at {done['completed_at']}")
    return 0


def _daily_run(args: argparse.Namespace, api: ApiClient) -> int:
    """The whole day in one command. Only the feedback step can reach the coach, and only without
    `--no-generate`. A failed analysis prints its safe error and the day still goes on: feedback
    marks the skill it could not score, and the session completes. The exit code stays 1 so a
    script sees the failure. A job that did not finish in time stops the run (feedback would be
    refused anyway)."""
    if not Path(args.wav).is_file():
        print(
            "cannot read the recording: the file does not exist or is not a file", file=sys.stderr
        )
        return 2
    body = api.post_json("/api/plan/today/session")
    for line in _daily_start_lines(body):
        print(line)
    session = _record(body, "session_id", "attempts")
    first = _record(cast(list[object], session["attempts"])[0], "id")
    code = _follow(api, api.upload_wav(str(first["id"]), Path(args.wav)))
    if code not in (0, 1):
        return code
    session_id = str(session["session_id"])
    path = _session_path(session_id, "feedback")
    body = api.get_json(path) if args.no_generate else api.post_json(path)
    for line in _feedback_lines(body):
        print(line)
    completed = _complete(api, session_id)
    return code or completed


def _plan(args: argparse.Namespace, api: ApiClient) -> int:
    body = api.post_json("/api/plan/today")
    if args.json:
        print(json.dumps(body, indent=2, sort_keys=True))
    else:
        for line in _plan_lines(body):
            print(line)
    return 0


def _job(args: argparse.Namespace, api: ApiClient) -> int:
    if args.resume:
        api.resume_job(args.job_id)
    if args.follow:
        return _follow(api, args.job_id)
    job = api.get_job(args.job_id)
    for step in _steps(job):
        if step["state"] != "pending":
            print(progress_line(step["name"], step["state"], job["progress"], step.get("message")))
    if job["status"] in TERMINAL:
        return _finish(args.job_id, job)
    print(f"job {args.job_id} {job['status']}")
    return 0


def _api_command(
    args: argparse.Namespace,
    settings: Settings,
    client: ApiClient | None,
    synthesizer: Synthesizer | None,
) -> int:
    """`upload`, `job` and the first-run commands: all talk to the running API, through `client`
    or a new one. `stand-in` alone needs a synthesizer, built here when none was given."""
    if args.command == "upload" and args.new_attempt and settings.data_dir == REPO_ROOT / "data":
        print(
            "refusing to create an attempt in the real data directory; set NOSOLEAR_DATA_DIR to a"
            " separate location, e.g. NOSOLEAR_DATA_DIR=data/dev",
            file=sys.stderr,
        )
        return 2
    if args.command == "upload" and not Path(args.file).is_file():
        print(
            "cannot read the recording: the file does not exist or is not a file", file=sys.stderr
        )
        return 2
    creates_attempt = args.command == "upload" and args.new_attempt
    attempt_id: str | None = args.attempt_id if args.command == "upload" else None
    try:
        prepare_process(settings, create_data_dir=creates_attempt)
        if creates_attempt:
            attempt_id = _create_attempt(settings)
    except DataDirError as exc:
        print(f"data directory problem: {exc}", file=sys.stderr)
        return 2
    if creates_attempt:
        print(f"attempt {attempt_id}")
    owned = client is None
    api = client or ApiClient(
        httpx.Client(
            base_url=args.base_url or f"http://{settings.host}:{settings.port}",
            timeout=API_TIMEOUT_S,
        )
    )
    try:
        if args.command == "upload":
            return _upload(args, api, attempt_id)
        if args.command == "plan":
            return _plan(args, api)
        if args.command == "daily":
            if args.daily_command == "feedback":
                return _daily_feedback(args, api)
            if args.daily_command == "complete":
                return _complete(api, args.session_id)
            if args.daily_command == "run":
                return _daily_run(args, api)
            return _daily_start(api)
        if args.command == first_run_cli.STAND_IN and synthesizer is None:
            synthesizer = build_stand_in_synthesizer(settings)
        handled = first_run_cli.run(args, api, synthesizer=synthesizer, data_dir=settings.data_dir)
        return _job(args, api) if handled is None else handled
    except CliError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    finally:
        if owned:
            api.close()


def _doctor_probe(settings: Settings) -> int:
    """`doctor --probe`: makes paid calls, so only the user runs it. Prints one line per probe,
    stores what each measured, then prints the readiness report. Exit 1 if any probe failed."""
    try:
        prepare_process(settings, create_data_dir=True)
    except DataDirError as exc:
        print(f"data directory problem: {exc}", file=sys.stderr)
        return 2
    engine = create_engine_for(settings.database_url)
    try:
        upgrade_to_head(engine)
        clock = SystemClock()
        store = CapabilityRepository(engine)
        ledger = build_ledger(settings, engine, clock=clock)
        try:
            providers = build_providers(
                settings,
                engine=engine,
                ledger=ledger,
                clock=clock,
                real_time_factors=real_time_factors(store.latest_all()),
            )
            probes = build_capability_probes(settings, providers, engine=engine, clock=clock)
        except NosolearError as exc:
            print(f"doctor --probe could not start: {exc.safe_message}", file=sys.stderr)
            return 1
        except Exception as exc:
            logging.getLogger(__name__).warning("probe setup failed (%s)", type(exc).__name__)
            print(
                "doctor --probe could not start: the probe setup failed unexpectedly",
                file=sys.stderr,
            )
            return 1
        outcomes = probe_capabilities(probes=probes, store=store)
        for outcome in outcomes:
            status = "ok" if outcome.ok else "failed"
            print(f"{status}  {outcome.adapter}: {outcome.message}")
        report = check_readiness(
            settings,
            get_environment(),
            usage=read_usage(settings),
            capability_records=store.latest_all(),
        )
        print(format_readiness(report))
        return 0 if all(outcome.ok for outcome in outcomes) else 1
    finally:
        engine.dispose()


def main(
    argv: Sequence[str] | None = None,
    *,
    client: ApiClient | None = None,
    synthesizer: Synthesizer | None = None,
) -> int:
    args = _parser().parse_args(argv)
    try:
        settings = Settings()
    except ValidationError as exc:
        print(f"invalid settings:\n{settings_error_summary(exc)}", file=sys.stderr)
        return 2
    except UnicodeDecodeError:
        print("cannot read settings: .env is not valid UTF-8", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"cannot read settings: {exc.strerror or type(exc).__name__}", file=sys.stderr)
        return 2
    if args.command == "serve":
        import uvicorn

        try:
            prepare_process(settings, create_data_dir=True)
        except DataDirError as exc:
            print(f"data directory problem: {exc}", file=sys.stderr)
            return 2

        uvicorn.run(
            "nosolear.api.app:create_app",
            factory=True,
            host=settings.host,
            port=settings.port,
            reload=args.reload,
            proxy_headers=False,
        )
        return 0
    if args.command == "doctor":
        if args.probe:
            return _doctor_probe(settings)
        prepare_process(settings, create_data_dir=False)
        report = check_readiness(
            settings,
            get_environment(),
            usage=read_usage(settings),
            capability_records=read_capabilities(settings),
        )
        print(format_readiness(report))
        return 0 if report.ready else 1
    if args.command in (
        "upload",
        "job",
        "plan",
        "daily",
        first_run_cli.RESCORE,
        first_run_cli.CALIBRATE,
        first_run_cli.BASELINE,
        first_run_cli.ONBOARDING,
        first_run_cli.STAND_IN,
    ):
        return _api_command(args, settings, client, synthesizer)
    if args.command == "dev-seed" and settings.data_dir == REPO_ROOT / "data":
        print(
            "refusing to seed the real data directory (the observation log has no delete path);"
            " set NOSOLEAR_DATA_DIR to a separate location, e.g. NOSOLEAR_DATA_DIR=data/dev",
            file=sys.stderr,
        )
        return 2
    try:
        prepare_process(settings, create_data_dir=True)
    except DataDirError as exc:
        print(f"data directory problem: {exc}", file=sys.stderr)
        return 2
    pack: LanguagePack | None = None
    if args.command in ("rebuild-profile", "dev-seed"):
        try:
            pack = load_active_pack(settings)
        except PackError as exc:
            print(f"pack error: {exc}", file=sys.stderr)
            return 2
    engine = create_engine_for(settings.database_url)
    try:
        if args.command == "db":
            upgrade_to_head(engine)
        elif args.command == "rebuild-profile":
            if pack is None:
                print("pack error: the language pack was not loaded", file=sys.stderr)
                return 2
            _rebuild(engine, pack)
        elif args.command == "dev-seed":
            observations = ObservationRepository(engine)
            if observations.all() and not args.force:
                print("observations already exist; use --force", file=sys.stderr)
                return 2
            observations.add_many(
                seed_observations(days=args.days, seed=args.seed, end=SystemClock().now())
            )
            if pack is None:
                print("pack error: the language pack was not loaded", file=sys.stderr)
                return 2
            _rebuild(engine, pack)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
