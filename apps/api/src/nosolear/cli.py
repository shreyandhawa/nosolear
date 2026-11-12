"""Command-line entry point and composition root for the `nosolear` command."""

import argparse
import sys
from collections.abc import Sequence

from pydantic import ValidationError
from sqlalchemy import Engine

from nosolear.adapters.system_clock import SystemClock
from nosolear.app.rebuild_profile import rebuild_profile
from nosolear.dev.seed import seed_observations
from nosolear.domain.taxonomy import DEFAULT_TAXONOMY
from nosolear.persistence.db import create_engine_for, upgrade_to_head
from nosolear.persistence.repositories import ObservationRepository, ProfileRepository
from nosolear.settings import REPO_ROOT, Settings, settings_error_summary


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
    return parser


def _rebuild(engine: Engine) -> None:
    profile = rebuild_profile(
        observations=ObservationRepository(engine),
        profiles=ProfileRepository(engine, DEFAULT_TAXONOMY),
        taxonomy=DEFAULT_TAXONOMY,
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
    if args.command == "dev-seed" and settings.data_dir == REPO_ROOT / "data":
        print(
            "refusing to seed the real data directory (the observation log has no delete path);"
            " set NOSOLEAR_DATA_DIR to a separate location, e.g. NOSOLEAR_DATA_DIR=data/dev",
            file=sys.stderr,
        )
        return 2
    engine = create_engine_for(settings.database_url)
    try:
        if args.command == "db":
            upgrade_to_head(engine)
        elif args.command == "rebuild-profile":
            _rebuild(engine)
        elif args.command == "dev-seed":
            observations = ObservationRepository(engine)
            if observations.all() and not args.force:
                print("observations already exist; use --force", file=sys.stderr)
                return 2
            observations.add_many(
                seed_observations(days=args.days, seed=args.seed, end=SystemClock().now())
            )
            _rebuild(engine)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    sys.exit(main())
