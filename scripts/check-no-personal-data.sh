#!/usr/bin/env bash
# Reads newline-separated paths on stdin; exits 1 if any is audio, a SQLite/DB file (with or
# without its -wal/-shm/-journal sidecar), or under a data/ directory at any depth.
bad=$(grep -iE '(\.(wav|webm|ogg|m4a|mp3|flac|aiff|aif|caf|aac|opus|mp4|m4b|amr|3gp)$|\.(sqlite3?|db)(-(wal|shm|journal))?$|(^|/)data/)' || true)
if [ -n "$bad" ]; then
  echo "Refusing: personal data must not be committed:" >&2
  echo "$bad" >&2
  exit 1
fi
