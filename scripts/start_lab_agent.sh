#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
OWNER_UID="${SUDO_UID:-${CCREPLAY_OWNER_UID:-}}"
OWNER_GID="${SUDO_GID:-${CCREPLAY_OWNER_GID:-}}"
if [[ "$(id -u)" != 0 || -z "$OWNER_UID" || "$OWNER_UID" == 0 || -z "$OWNER_GID" || "$OWNER_GID" == 0 ]]; then
  echo 'Start from a normal-user terminal: sudo bash scripts/start_lab_agent.sh' >&2
  echo 'A root-only session must first configure a normal login user and put the checkout in that user’s accessible workspace.' >&2
  exit 2
fi
exec .venv/bin/python -m ccreplay.lab_agent --uid "$OWNER_UID" --gid "$OWNER_GID" --socket "${CCREPLAY_LAB_SOCKET:-/tmp/ccreplay-lab-$OWNER_UID/agent.sock}"
