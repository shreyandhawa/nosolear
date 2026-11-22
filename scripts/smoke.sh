#!/usr/bin/env bash
# Manual end-to-end run on a throwaway data dir. Spends real Azure F0 audio (about 10 minutes).
set -euo pipefail

if [ -n "${CI:-}" ]; then
  echo "refusing to run in CI: make smoke spends real Azure audio" >&2
  exit 2
fi

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# A free port, so another server on this machine never collides with the run.
PORT="$(python3 -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])')"
# shortcut: this run is metered against its own fresh ledger, so its spend never counts toward
# data/'s caps; both usage lines are printed instead. Upgrade if smoke runs become frequent.
if [ -d "$ROOT/data" ]; then
  echo "data/ usage before this run (this run is NOT counted there):"
  (cd "$ROOT/apps/api" && NOSOLEAR_DATA_DIR="$ROOT/data" uv run nosolear doctor 2>/dev/null | grep '^Usage') || true
fi
# Assigned before export, so a mktemp failure stops the run instead of falling back to data/.
DATA_DIR="$(mktemp -d)"
export NOSOLEAR_DATA_DIR="$DATA_DIR"
export NOSOLEAR_PORT="$PORT"
LOG="$NOSOLEAR_DATA_DIR/server.log"
# The client commands find the server through NOSOLEAR_PORT; .env (REPO_ROOT/.env) loads keys.
BASE="http://127.0.0.1:$PORT"
cd "$ROOT/apps/api"

uv run nosolear serve >"$LOG" 2>&1 &
SERVER=$!
trap 'kill "$SERVER" 2>/dev/null || true; echo "data dir: $NOSOLEAR_DATA_DIR"; echo "server log: $LOG"; uv run nosolear doctor 2>/dev/null | grep "^Usage" || true' EXIT

for _ in $(seq 60); do
  curl -fs "$BASE/api/health" >/dev/null 2>&1 && break
  kill -0 "$SERVER" 2>/dev/null || { echo "server exited early; see $LOG" >&2; exit 1; }
  sleep 1
done
curl -fs "$BASE/api/health" >/dev/null || { echo "server did not answer; see $LOG" >&2; exit 1; }

step() {
  echo "==> nosolear $*"
  uv run nosolear "$@" || { echo "smoke FAILED at: nosolear $*" >&2; exit 1; }
}

echo "==> nosolear doctor --probe"
uv run nosolear doctor --probe || { echo "smoke FAILED at: doctor --probe" >&2; exit 1; }
step calibrate start
step stand-in calibration
step calibrate finish
step baseline start
step stand-in baseline
step baseline complete
step baseline report
step plan
step stand-in daily
