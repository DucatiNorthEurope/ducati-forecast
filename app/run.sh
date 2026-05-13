#!/usr/bin/env bash
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
PARENT_DIR="$(dirname "$APP_DIR")"
REQUIREMENTS="$APP_DIR/../requirements.txt"
[ -f "$REQUIREMENTS" ] || REQUIREMENTS="$APP_DIR/requirements.txt"
if [ ! -d "$APP_DIR/venv" ]; then
  python3 -m venv "$APP_DIR/venv"
  "$APP_DIR/venv/bin/pip" install --upgrade pip
  "$APP_DIR/venv/bin/pip" install -r "$REQUIREMENTS"
fi
cd "$PARENT_DIR"
exec "$APP_DIR/venv/bin/python" -m app.app
