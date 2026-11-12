"""Regenerate the dependency licence tables in THIRD_PARTY_NOTICES.

Run from the repo root:

    uv run --project apps/api python scripts/third_party_licences.py          # rewrite
    uv run --project apps/api python scripts/third_party_licences.py --check  # exit 1 on drift

Python rows come from the installed metadata of the project environment, web rows from
`pnpm licenses list --json` in apps/web. Nothing here touches the network.
"""

import json
import re
import subprocess
import sys
import tomllib
from importlib import metadata
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
NOTICES = ROOT / "THIRD_PARTY_NOTICES"
UNKNOWN = "UNKNOWN: check upstream"
# Locked for other platforms only, so not installed here; licence read from its upstream.
OVERRIDES = {"colorama": "BSD-3-Clause"}
HEADER = "| Name | Version | Licence |\n|---|---|---|"


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


def python_rows() -> list[tuple[str, str, str]]:
    lock = tomllib.loads((ROOT / "apps/api/uv.lock").read_text(encoding="utf-8"))
    installed = {normalize(d.metadata["Name"]): d for d in metadata.distributions()}
    rows: list[tuple[str, str, str]] = []
    for package in lock["package"]:
        name = normalize(package["name"])
        if name == "nosolear":
            continue
        dist = installed.get(name)
        licence = python_licence(dist) if dist else OVERRIDES.get(name, UNKNOWN)
        rows.append((name, package["version"], licence))
    return sorted(rows)


def web_rows() -> list[tuple[str, str, str]]:
    out = subprocess.run(
        ["pnpm", "licenses", "list", "--json"],
        cwd=ROOT / "apps/web",
        check=True,
        capture_output=True,
        text=True,
    ).stdout
    rows: set[tuple[str, str, str]] = set()
    for licence, packages in json.loads(out).items():
        for package in packages:
            rows.update((package["name"], v, licence) for v in package["versions"])
    return sorted(rows)


def table(rows: list[tuple[str, str, str]]) -> str:
    body = "\n".join(f"| {name} | {version} | {licence} |" for name, version, licence in rows)
    return f"{HEADER}\n{body}"


def replace_block(text: str, marker: str, content: str) -> str:
    pattern = re.compile(rf"(<!-- {marker}:start -->\n).*?(\n<!-- {marker}:end -->)", re.DOTALL)
    if not pattern.search(text):
        raise SystemExit(f"{NOTICES.name}: missing <!-- {marker}:start/end --> markers")
    return pattern.sub(lambda m: f"{m.group(1)}{content}{m.group(2)}", text)


def main() -> int:
    current = NOTICES.read_text(encoding="utf-8")
    updated = replace_block(current, "python-dependencies", table(python_rows()))
    updated = replace_block(updated, "web-dependencies", table(web_rows()))
    if "--check" in sys.argv[1:]:
        if updated != current:
            print(f"{NOTICES.name} is out of date. Run scripts/third_party_licences.py.")
            return 1
        return 0
    NOTICES.write_text(updated, encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
