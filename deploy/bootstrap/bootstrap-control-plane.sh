#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/control-plane.env}"
TARGET_DIR="${CONTROL_PLANE_TARGET_DIR:-/opt/control-panel-container}"
# shellcheck source=./lib.sh
source "$ROOT_DIR/deploy/bootstrap/lib.sh"

load_env_file "$ENV_FILE"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on control-plane host"
  exit 1
fi

log_phase "control-plane host preflight"
wait_for_apt_locks
apt_get_safe update >/dev/null
apt_get_safe install -y docker-compose-v2 >/dev/null || apt_get_safe install -y docker-compose-plugin >/dev/null || true
if [[ -n "${XRAY_RELAY_HOST:-}" && -n "${XRAY_RELAY_PORT:-}" ]]; then
  log_phase "control-plane relay readiness check"
  wait_for_tcp_endpoint "$XRAY_RELAY_HOST" "$XRAY_RELAY_PORT"
fi
log_phase "stage control-plane runtime"
mkdir -p "$TARGET_DIR"
find "$TARGET_DIR" -mindepth 1 -maxdepth 1 \
  ! -name runtime \
  -exec rm -rf {} +
cp -a "$ROOT_DIR/." "$TARGET_DIR/"

cp "$ENV_FILE" "$TARGET_DIR/.env"

cd "$TARGET_DIR"
log_phase "apply control-plane compose stack"
docker compose up -d --build

docker compose ps
