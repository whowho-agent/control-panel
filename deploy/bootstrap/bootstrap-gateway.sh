#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/gateway.env}"
TEMPLATE="$ROOT_DIR/deploy/templates/xray-frontend.config.json.template"
# shellcheck source=./lib.sh
source "$ROOT_DIR/deploy/bootstrap/lib.sh"

load_env_file "$ENV_FILE"
require_env_vars \
  XRAY_FRONTEND_PORT \
  XRAY_FRONTEND_SERVER_NAME \
  XRAY_FRONTEND_TARGET \
  XRAY_FRONTEND_FINGERPRINT \
  XRAY_FRONTEND_SHORT_IDS \
  XRAY_FRONTEND_REALITY_PRIVATE_KEY \
  XRAY_RELAY_HOST \
  XRAY_RELAY_PORT \
  XRAY_RELAY_UUID

export XRAY_FRONTEND_ACCESS_LOG_PATH="${XRAY_FRONTEND_ACCESS_LOG_PATH:-/opt/xray-frontend/access.log}"
export XRAY_FRONTEND_ERROR_LOG_PATH="${XRAY_FRONTEND_ERROR_LOG_PATH:-/opt/xray-frontend/error.log}"
export XRAY_FRONTEND_SPIDER_X="${XRAY_FRONTEND_SPIDER_X:-/}"
export XRAY_FRONTEND_SHORT_IDS_JSON="$(python3 - <<'PY'
import json, os
print(', '.join(json.dumps(item.strip()) for item in os.environ['XRAY_FRONTEND_SHORT_IDS'].split(',') if item.strip()))
PY
)"

log_phase "gateway host preflight"
sudo bash -c "$(declare -f wait_for_apt_locks); $(declare -f apt_get_safe); $(declare -f install_apt_packages); install_apt_packages qrencode curl gettext-base"
if [[ ! -x /opt/xray-frontend/xray ]]; then
  log_phase "install xray frontend binary"
  sudo bash -c "$(declare -f wait_for_apt_locks); $(declare -f apt_get_safe); $(declare -f install_apt_packages); $(declare -f install_xray_binary); install_xray_binary /opt/xray-frontend"
fi
sudo chmod 755 /opt/xray-frontend/xray

log_phase "gateway readiness checks"
sudo install -d -m 755 /opt/xray-frontend
sudo install -d -m 755 "$(dirname "$XRAY_FRONTEND_ACCESS_LOG_PATH")" "$(dirname "$XRAY_FRONTEND_ERROR_LOG_PATH")"
sudo touch "$XRAY_FRONTEND_ACCESS_LOG_PATH" "$XRAY_FRONTEND_ERROR_LOG_PATH" /opt/xray-frontend/clients-meta.json
sudo ROOT_DIR="$ROOT_DIR" TCP_WAIT_TIMEOUT="$TCP_WAIT_TIMEOUT" TCP_WAIT_INTERVAL="$TCP_WAIT_INTERVAL" bash -lc 'source "$ROOT_DIR/deploy/bootstrap/lib.sh"; wait_for_tcp_endpoint "$0" "$1"' "$XRAY_RELAY_HOST" "$XRAY_RELAY_PORT"

log_phase "render and apply gateway config"
envsubst < "$TEMPLATE" | sudo tee /opt/xray-frontend/config.json >/dev/null
sudo python3 "$ROOT_DIR/deploy/bootstrap/restore_clients.py" \
  /opt/xray-frontend/config.json \
  /opt/xray-frontend/clients-meta.json

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
