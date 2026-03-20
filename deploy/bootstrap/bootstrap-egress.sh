#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/egress.env}"
TEMPLATE="$ROOT_DIR/deploy/templates/xray-relay.config.json.template"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "egress env file not found: $ENV_FILE"
  exit 1
fi

source "$ENV_FILE"

: "${XRAY_RELAY_PORT:?}"
: "${XRAY_RELAY_UUID:?}"

sudo apt-get update >/dev/null
sudo apt-get install -y curl >/dev/null
sudo install -d -m 755 /opt/xray-relay
if [[ ! -f /opt/xray-relay/xray ]]; then
  echo "place xray binary at /opt/xray-relay/xray before running bootstrap"
  exit 1
fi
sudo chmod 755 /opt/xray-relay/xray

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
sudo systemctl status xray-relay --no-pager -l | sed -n '1,20p'
