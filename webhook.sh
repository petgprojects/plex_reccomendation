#!/bin/sh

set -eu

SCRIPTS_DIR="$(dirname "$0")"
echo $SCRIPTS_DIR
VENV_DIR="$SCRIPTS_DIR/plex_recs_env"
REQ_FILE="$SCRIPTS_DIR/requirements.txt"

if [ ! -d "$VENV_DIR" ]; then
    echo "[webhook] Creating venv in $VENV_DIR"
    python3 -m venv "$VENV_DIR"
fi

if [ ! -d "$VENV_DIR/bin" ]; then
    PYTHON_DIR="$VENV_DIR/Scripts"
    # "$VENV_DIR/Scripts/pip" install --no-cache-dir -r "$REQ_FILE"
else
    PYTHON_DIR="$VENV_DIR/bin"
    # "$VENV_DIR/bin/pip" install --no-cache-dir -r "$REQ_FILE"
fi

STAMP="$VENV_DIR/.__installed"
if [ "$REQ_FILE" -nt "$STAMP" ]; then
    echo "[webhook] Installing / updating Python deps …"
    "$PYTHON_DIR/pip" install --no-cache-dir -r "$REQ_FILE"
    touch "$STAMP"
fi

if [ -f "$SCRIPTS_DIR/.env" ]; then
    # shellcheck source=/dev/null
    . "$SCRIPTS_DIR/.env"
fi

exec "$PYTHON_DIR/python" "$SCRIPTS_DIR/tautulli_webhook.py" "$@"