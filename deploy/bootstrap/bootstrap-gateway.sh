#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/gateway.env}"
TEMPLATE="$ROOT_DIR/deploy/templates/xray-frontend.config.json.template"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "gateway env file not found: $ENV_FILE"
  exit 1
fi

source "$ENV_FILE"

: "${XRAY_FRONTEND_PORT:?}"
: "${XRAY_FRONTEND_SERVER_NAME:?}"
: "${XRAY_FRONTEND_TARGET:?}"
: "${XRAY_FRONTEND_FINGERPRINT:?}"
: "${XRAY_FRONTEND_SHORT_IDS:?}"
: "${XRAY_FRONTEND_REALITY_PRIVATE_KEY:?}"
: "${XRAY_RELAY_HOST:?}"
: "${XRAY_RELAY_PORT:?}"
: "${XRAY_RELAY_UUID:?}"

export XRAY_FRONTEND_ACCESS_LOG_PATH="${XRAY_FRONTEND_ACCESS_LOG_PATH:-/opt/xray-frontend/access.log}"
export XRAY_FRONTEND_ERROR_LOG_PATH="${XRAY_FRONTEND_ERROR_LOG_PATH:-/opt/xray-frontend/error.log}"
export XRAY_FRONTEND_SPIDER_X="${XRAY_FRONTEND_SPIDER_X:-/}"
export XRAY_FRONTEND_SHORT_IDS_JSON="$(python3 - <<'PY'
import json, os
print(', '.join(json.dumps(item.strip()) for item in os.environ['XRAY_FRONTEND_SHORT_IDS'].split(',') if item.strip()))
PY
)"

sudo apt-get update >/dev/null
sudo apt-get install -y qrencode curl >/dev/null
sudo install -d -m 755 /opt/xray-frontend
if [[ ! -f /opt/xray-frontend/xray ]]; then
  echo "place xray binary at /opt/xray-frontend/xray before running bootstrap"
  exit 1
fi
sudo chmod 755 /opt/xray-frontend/xray

envsubst < "$TEMPLATE" | sudo tee /opt/xray-frontend/config.json >/dev/null
sudo touch "$XRAY_FRONTEND_ACCESS_LOG_PATH" "$XRAY_FRONTEND_ERROR_LOG_PATH"

sudo tee /etc/systemd/system/xray-frontend.service >/dev/null <<'EOF'
[Unit]
Description=Standalone Xray Frontend
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/xray-frontend
ExecStart=/opt/xray-frontend/xray run -c /opt/xray-frontend/config.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now xray-frontend
sudo systemctl status xray-frontend --no-pager -l | sed -n '1,20p'
