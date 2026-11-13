#!/usr/bin/env bash
# Reads newline-separated paths on stdin; exits 1 if any is audio, a SQLite/DB file (with or
# without its -wal/-shm/-journal sidecar), a .env or .env.<name> file at any depth (except
# .env.example), or under a data/ directory at any depth.
paths=$(cat)
bad=$(
  {
    printf '%s\n' "$paths" | grep -iE '(\.(wav|webm|ogg|m4a|mp3|flac|aiff|aif|caf|aac|opus|mp4|m4b|amr|3gp)$|\.(sqlite3?|db)(-(wal|shm|journal))?$|(^|/)data/)'
    printf '%s\n' "$paths" | grep -iE '(^|/)\.env(\.[^/]*)?$' | grep -viE '(^|/)\.env\.example$'
  } || true
)
if [ -n "$bad" ]; then
  echo "Refusing: personal data must not be committed:" >&2
  echo "$bad" >&2
  exit 1
fi
