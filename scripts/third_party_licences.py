"""Regenerate the dependency licence tables in THIRD_PARTY_NOTICES.

Run from the repo root:

    uv run --project apps/api python scripts/third_party_licences.py          # rewrite
    uv run --project apps/api python scripts/third_party_licences.py --check  # exit 1 on drift

Python rows come from the installed metadata of the project environment, web rows from
`pnpm licenses list --json` in apps/web. Nothing here touches the network.
"""

import argparse
import json
import re
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTICES = ROOT / "THIRD_PARTY_NOTICES"
COMMAND = "uv run --project apps/api python scripts/third_party_licences.py"
UNKNOWN = "UNKNOWN: check upstream"
# Locked for other platforms only, so not installed on every machine. colorama is
# BSD-3-Clause: https://github.com/tartley/colorama/blob/master/LICENSE.txt (checked 2026-11-12).
OVERRIDES = {"colorama": "BSD-3-Clause"}
HEADER = "| Name | Version | Licence |\n|---|---|---|"

Row = tuple[str, str, str]


class ScriptError(Exception):
    """A problem with the environment or its inputs (exit code 2), not table drift."""


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def python_licence(dist: metadata.Distribution) -> str:
    meta = dist.metadata
    expression = meta.get("License-Expression")
    if expression:
        return expression
    field = (meta.get("License") or "").strip()
    if field and "\n" not in field and len(field) <= 80 and field.upper() != "UNKNOWN":
        return field
    classifiers = [
        c.rsplit("::", 1)[1].strip()
        for c in meta.get_all("Classifier") or []
        if c.startswith("License ::")
    ]
    return " OR ".join(sorted(classifiers)) or UNKNOWN


def python_rows() -> list[Row]:
    lock = tomllib.loads((ROOT / "apps/api/uv.lock").read_text(encoding="utf-8"))
    installed = {normalize(d.metadata["Name"]): d for d in metadata.distributions()}
    rows: list[Row] = []
    stale: list[str] = []
    for package in lock["package"]:
        name = normalize(package["name"])
        if name == "nosolear":
            continue
        dist = installed.get(name)
        if dist is None:
            licence = OVERRIDES.get(name, UNKNOWN)
            if licence == UNKNOWN:
                print(f"warning: {name} is locked but not installed", file=sys.stderr)
        else:
            licence = python_licence(dist)
            if dist.version != package["version"]:
                stale.append(f"{name} (installed {dist.version}, locked {package['version']})")
        rows.append((name, package["version"], licence))
    if stale:
        raise ScriptError(
            "installed packages differ from uv.lock: " + ", ".join(stale) + ". Run `uv sync`."
        )
    return sorted(rows)


def web_rows() -> list[Row]:
    web = ROOT / "apps/web"
    try:
        out = subprocess.run(
            ["pnpm", "licenses", "list", "--json"],
            cwd=web,
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    except FileNotFoundError as error:
        raise ScriptError("pnpm not found; install pnpm first") from error
    except subprocess.CalledProcessError as error:
        raise ScriptError(
            f"pnpm licenses failed:\n{error.stderr}\nRun `pnpm install` in apps/web first."
        ) from error
    try:
        data = json.loads(out)
        rows = {
            (package["name"], version, licence)
            for licence, packages in data.items()
            for package in packages
            for version in package["versions"]
        }
    except (json.JSONDecodeError, AttributeError, KeyError, TypeError) as error:
        raise ScriptError(f"could not parse `pnpm licenses list --json`: {error!r}") from error
    if not rows:
        raise ScriptError("pnpm reported no packages; run `pnpm install` in apps/web")
    package_json = json.loads((web / "package.json").read_text(encoding="utf-8"))
    direct = set(package_json.get("dependencies", {})) | set(
        package_json.get("devDependencies", {})
    )
    missing = direct - {name for name, _, _ in rows}
    if missing:
        raise ScriptError(
            "pnpm result lacks direct dependencies: "
            + ", ".join(sorted(missing))
            + ". Run `pnpm install` in apps/web."
        )
    return sorted(rows)


def table(rows: list[Row]) -> str:
    body = "\n".join(f"| {name} | {version} | {licence} |" for name, version, licence in rows)
    return f"{HEADER}\n{body}"


def replace_block(text: str, marker: str, content: str) -> str:
    pattern = re.compile(rf"(<!-- {marker}:start -->\n).*?(\n<!-- {marker}:end -->)", re.DOTALL)
    if not pattern.search(text):
        raise ScriptError(f"{NOTICES.name}: missing <!-- {marker}:start/end --> markers")
    return pattern.sub(lambda m: f"{m.group(1)}{content}{m.group(2)}", text)


def run(check: bool) -> int:
    tables = {"python-dependencies": python_rows(), "web-dependencies": web_rows()}
    unknown = [
        f"{name} {version}"
        for rows in tables.values()
        for name, version, licence in rows
        if licence.startswith("UNKNOWN")
    ]
    if unknown:
        raise ScriptError("licence unknown for: " + ", ".join(unknown) + ". Check upstream.")
    current = NOTICES.read_text(encoding="utf-8")
    updated = current
    drifted: list[str] = []
    for marker, rows in tables.items():
        new = replace_block(updated, marker, table(rows))
        if new != updated:
            drifted.append(marker)
        updated = new
    if check:
        if drifted:
            print(
                f"{NOTICES.name} is out of date ({', '.join(drifted)}). Run: {COMMAND}",
                file=sys.stderr,
            )
            return 1
        return 0
    if drifted:
        NOTICES.write_text(updated, encoding="utf-8")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    parser.add_argument(
        "--check", action="store_true", help="exit 1 if the tables differ; write nothing"
    )
    args = parser.parse_args(argv)
    try:
        return run(args.check)
    except ScriptError as error:
        print(f"error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
