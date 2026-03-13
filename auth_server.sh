#!/bin/sh

set -eu

SCRIPTS_DIR="$(dirname "$0")"
VENV_DIR="$SCRIPTS_DIR/plex_recs_env"
REQ_FILE="$SCRIPTS_DIR/requirements.txt"

if [ ! -f "$REQ_FILE" ]; then
  echo "[auth_server] ERROR: requirements.txt not found at $REQ_FILE"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
  echo "[auth_server] Creating venv in $VENV_DIR"
  python3 -m venv "$VENV_DIR"
fi

if [ -d "$VENV_DIR/bin" ]; then
  PYTHON_DIR="$VENV_DIR/bin"
else
  PYTHON_DIR="$VENV_DIR/Scripts"
fi

STAMP="$VENV_DIR/.__installed"

if [ ! -f "$STAMP" ] || [ "$REQ_FILE" -nt "$STAMP" ]; then
  echo "[auth_server] Installing / updating Python deps ..."
  "$PYTHON_DIR/pip" install --no-cache-dir -r "$REQ_FILE"
  touch "$STAMP"
fi

if [ -f "$SCRIPTS_DIR/.env" ]; then
  # shellcheck source=/dev/null
  . "$SCRIPTS_DIR/.env"
fi

exec "$PYTHON_DIR/python" "$SCRIPTS_DIR/auth_server.py" "$@"
