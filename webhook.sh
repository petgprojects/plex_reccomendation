#!/bin/sh

set -eu

SCRIPTS_DIR="$(dirname "$0")"
echo $SCRIPTS_DIR
VENV_DIR="$SCRIPTS_DIR/plex_recs_env"
echo "venv dir: $VENV_DIR"
REQ_FILE="$SCRIPTS_DIR/requirements.txt"
echo "req file: $REQ_FILE"

if [ ! -f "$REQ_FILE" ]; then
  echo "[webhook] ERROR: requirements.txt not found at $REQ_FILE"
  echo "[webhook]        Did you mount the correct folder into the container?"
  exit 1
fi

if [ ! -d "$VENV_DIR" ]; then
    echo "[webhook] Creating venv in $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR/bin" ]; then
    PYTHON_DIR="$VENV_DIR/Scripts"
else
    PYTHON_DIR="$VENV_DIR/bin"
fi

echo "python dir: $PYTHON_DIR"

STAMP="$VENV_DIR/.__installed"

echo "stamp: $STAMP"

if [ ! -f "$STAMP" ] || [ "$REQ_FILE" -nt "$STAMP" ]; then
    echo "[webhook] Installing / updating Python deps …"
    "$PYTHON_DIR/pip" install --no-cache-dir -r "$REQ_FILE"
    touch "$STAMP"
fi

if [ -f "$SCRIPTS_DIR/.env" ]; then
    # shellcheck source=/dev/null
    . "$SCRIPTS_DIR/.env"
fi

exec "$PYTHON_DIR/python" "$SCRIPTS_DIR/tautulli_webhook.py" "$@"
