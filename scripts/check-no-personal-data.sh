#!/usr/bin/env bash
# Reads newline-separated paths on stdin; exits 1 if any is audio or under data/.
bad=$(grep -iE '(\.(wav|webm|ogg|m4a|mp3|flac)$|^data/)' || true)
if [ -n "$bad" ]; then
  echo "Refusing: personal data must not be committed:" >&2
  echo "$bad" >&2
  exit 1
fi
