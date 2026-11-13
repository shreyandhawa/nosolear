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
#
# The `local` and `apple` extras lock packages that are never installed in the dev environment,
# so their licences cannot come from installed metadata, and the script does not touch the
# network. Each row below is the licence in that package's PyPI metadata (read 2026-11-13), or
# its classifiers where the metadata names no expression. The NVIDIA CUDA wheels publish no
# licence metadata; they are marked "verify on the wheel" until someone reads the wheel's LICENSE.
# Add a row here whenever a new package appears in uv.lock: an unlisted one fails the run.
OVERRIDES = {
    "colorama": "BSD-3-Clause",
    "av": "BSD-3-Clause",
    "ctranslate2": "MIT",
    "cuda-bindings": "Apache-2.0",
    "cuda-pathfinder": "Apache-2.0",
    "cuda-toolkit": "NVIDIA proprietary (verify on the wheel)",
    "faster-whisper": "MIT",
    "filelock": "MIT",
    "flatbuffers": "Apache-2.0",
    "fsspec": "BSD-3-Clause",
    "hf-xet": "Apache-2.0",
    "httpcore2": "BSD-3-Clause",
    "httpx2": "BSD-3-Clause",
    "httpx2-jsfetch": "BSD-3-Clause",
    "huggingface-hub": "Apache-2.0",
    "jinja2": "BSD-3-Clause",
    "llvmlite": "BSD-2-Clause AND Apache-2.0 WITH LLVM-exception",
    "markdown-it-py": "MIT",
    "mdurl": "MIT",
    "mlx": "MIT",
    "mlx-metal": "MIT",
    "mlx-whisper": "MIT",
    "more-itertools": "MIT",
    "mpmath": "BSD-3-Clause",
    "networkx": "BSD-3-Clause",
    "numba": "BSD-2-Clause",
    "nvidia-cublas": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cuda-cccl": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cuda-cupti": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cuda-nvrtc": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cuda-runtime": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cudnn-cu13": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cufft": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cufile": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cusolver": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cusparse": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-cusparselt-cu13": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-nccl-cu13": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-nvjitlink": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-nvshmem-cu13": "NVIDIA proprietary (verify on the wheel)",
    "nvidia-nvtx": "NVIDIA proprietary (verify on the wheel)",
    "onnxruntime": "MIT",
    "packaging": "Apache-2.0 OR BSD-2-Clause",
    "protobuf": "BSD-3-Clause",
    "pygments": "BSD-2-Clause",
    "pyyaml": "MIT",
    "regex": "Apache-2.0 AND CNRI-Python",
    "rich": "MIT",
    "safetensors": "Apache-2.0",
    "setuptools": "MIT",
    "shellingham": "ISC",
    "sympy": "BSD-3-Clause",
    "tiktoken": "MIT",
    "tokenizers": "Apache-2.0",
    "torch": "Apache-2.0 AND Apache-2.0 WITH LLVM-exception AND BSD-2-Clause AND BSD-3-Clause AND BSL-1.0 AND ISC AND MIT AND Zlib",
    "tqdm": "MPL-2.0 AND MIT",
    "transformers": "Apache-2.0",
    "triton": "MIT",
    "truststore": "MIT",
    "typer": "MIT",
}
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
