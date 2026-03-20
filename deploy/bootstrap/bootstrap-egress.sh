#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/egress.env}"
TEMPLATE="$ROOT_DIR/deploy/templates/xray-relay.config.json.template"
# shellcheck source=./lib.sh
source "$ROOT_DIR/deploy/bootstrap/lib.sh"

require_env_file "$ENV_FILE"
set -a
source "$ENV_FILE"
set +a

: "${XRAY_RELAY_PORT:?}"
: "${XRAY_RELAY_UUID:?}"

sudo apt-get update >/dev/null
sudo apt-get install -y curl gettext-base >/dev/null
sudo install -d -m 755 /opt/xray-relay
if [[ ! -x /opt/xray-relay/xray ]]; then
  sudo bash -c "$(declare -f install_xray_binary); install_xray_binary /opt/xray-relay"
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
