#!/usr/bin/env bash
set -euo pipefail

APP_DIR=/opt/proxy-admin
BACKEND_DIR="$APP_DIR/backend"
FRONTEND_STATIC="$BACKEND_DIR/static"

mkdir -p "$APP_DIR"
python3 -m venv "$BACKEND_DIR/.venv"
"$BACKEND_DIR/.venv/bin/pip" install --upgrade pip
"$BACKEND_DIR/.venv/bin/pip" install -r "$BACKEND_DIR/requirements.txt"

install -m 0644 "$APP_DIR/deploy/proxy-admin.service" /etc/systemd/system/proxy-admin.service
systemctl daemon-reload
systemctl enable proxy-admin.service
systemctl restart proxy-admin.service
