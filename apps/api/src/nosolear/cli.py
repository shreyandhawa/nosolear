"""Command-line entry point and composition root for the `nosolear` command."""

import argparse
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy import Engine

from nosolear.adapters.private_fs import DataDirError
from nosolear.adapters.system_clock import SystemClock
from nosolear.api.deps import get_environment, load_active_pack
from nosolear.app.check_readiness import check_readiness
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.dev.seed import seed_observations
from nosolear.domain.packs import LanguagePack, PackError
from nosolear.domain.readiness import format_readiness
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.settings import REPO_ROOT, Settings, settings_error_summary
from nosolear.startup import prepare_process


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="nosolear")
    commands = parser.add_subparsers(dest="command", required=True)
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


def main(argv: Sequence[str] | None = None) -> int:
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
            print("probes arrive in Phase 0d", file=sys.stderr)
            return 2
        prepare_process(settings, create_data_dir=False)
        report = check_readiness(settings, get_environment())
        print(format_readiness(report))
        return 0 if report.ready else 1
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
            assert pack is not None
            _rebuild(engine, pack)
        elif args.command == "dev-seed":
            observations = ObservationRepository(engine)
            if observations.all() and not args.force:
                print("observations already exist; use --force", file=sys.stderr)
                return 2
            observations.add_many(
                seed_observations(days=args.days, seed=args.seed, end=SystemClock().now())
            )
            assert pack is not None
            _rebuild(engine, pack)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
