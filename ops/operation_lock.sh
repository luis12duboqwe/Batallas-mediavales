#!/usr/bin/env bash
# Exclusive host-local lock for deploy and operator-initiated rollback.
# Source only AFTER changing into the repository directory.
#
# Keep the file descriptor open in the caller until the whole operation exits.
# A second process must not race the first across release metadata or Docker.
umask 077
mkdir -p .ops-state
chmod 700 .ops-state

if [[ -L .ops-state/operation.lock ]]; then
  echo "Operation refused: lock path must not be a symbolic link" >&2
  exit 2
fi
exec 9>> .ops-state/operation.lock
chmod 600 .ops-state/operation.lock
if ! flock -n 9; then
  echo "Operation refused: deploy or rollback is already running" >&2
  exit 2
fi
