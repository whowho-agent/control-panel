#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/egress.env}"
TEMPLATE="$ROOT_DIR/deploy/templates/xray-relay.config.json.template"
# shellcheck source=./lib.sh
source "$ROOT_DIR/deploy/bootstrap/lib.sh"

load_env_file "$ENV_FILE"
require_env_vars XRAY_RELAY_PORT XRAY_RELAY_UUID

log_phase "egress host preflight"
sudo bash -c "$(declare -f wait_for_apt_locks); $(declare -f apt_get_safe); $(declare -f install_apt_packages); install_apt_packages curl gettext-base"
sudo install -d -m 755 /opt/xray-relay
if [[ ! -x /opt/xray-relay/xray ]]; then
  log_phase "install xray relay binary"
  sudo bash -c "$(declare -f wait_for_apt_locks); $(declare -f apt_get_safe); $(declare -f install_apt_packages); $(declare -f install_xray_binary); install_xray_binary /opt/xray-relay"
fi
sudo chmod 755 /opt/xray-relay/xray

log_phase "render and apply egress config"
envsubst < "$TEMPLATE" | sudo tee /opt/xray-relay/config.json >/dev/null

sudo tee /etc/systemd/system/xray-relay.service >/dev/null <<'EOF'
[Unit]
Description=Standalone Xray Relay
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=/opt/xray-relay
ExecStart=/opt/xray-relay/xray run -c /opt/xray-relay/config.json
Restart=on-failure
RestartSec=3
NoNewPrivileges=true

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl daemon-reload
sudo systemctl enable --now xray-relay
sudo ROOT_DIR="$ROOT_DIR" TCP_WAIT_TIMEOUT="$TCP_WAIT_TIMEOUT" TCP_WAIT_INTERVAL="$TCP_WAIT_INTERVAL" bash -lc 'source "$ROOT_DIR/deploy/bootstrap/lib.sh"; wait_for_tcp_endpoint 127.0.0.1 "$0"' "$XRAY_RELAY_PORT"
sudo systemctl status xray-relay --no-pager -l | sed -n '1,20p'
