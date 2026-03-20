#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/control-plane.env}"
TARGET_DIR="${CONTROL_PLANE_TARGET_DIR:-/opt/control-panel-container}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "control-plane env file not found: $ENV_FILE"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on control-plane host"
  exit 1
fi

apt-get update >/dev/null
apt-get install -y rsync docker-compose-plugin >/dev/null || true
mkdir -p "$TARGET_DIR"
rsync -az --delete \
  --exclude '.git' --exclude 'memory' --exclude 'keys' --exclude 'secrets' --exclude '.openclaw' \
  "$ROOT_DIR/" "$TARGET_DIR/"

cp "$ENV_FILE" "$TARGET_DIR/.env"
mkdir -p "$TARGET_DIR/runtime/frontend" "$TARGET_DIR/runtime/ssh"

ensure_runtime_file "/opt/xray-frontend/config.json" "$TARGET_DIR/runtime/frontend/config.json"
ensure_runtime_file "/opt/xray-frontend/access.log" "$TARGET_DIR/runtime/frontend/access.log"
ensure_runtime_file "/opt/xray-frontend/clients-meta.json" "$TARGET_DIR/runtime/frontend/clients-meta.json"
if [[ -x /opt/xray-frontend/xray ]]; then
  install -D -m 755 /opt/xray-frontend/xray "$TARGET_DIR/runtime/frontend/xray"
fi
if [[ -n "${XRAY_RELAY_SSH_KEY_SOURCE:-}" && -f "${XRAY_RELAY_SSH_KEY_SOURCE}" ]]; then
  install -D -m 600 "${XRAY_RELAY_SSH_KEY_SOURCE}" "$TARGET_DIR/runtime/ssh/relay_ssh_key"
fi

cd "$TARGET_DIR"
docker compose up -d --build

docker compose ps
