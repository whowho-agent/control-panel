#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_FILE="${1:-$ROOT_DIR/deploy/env/control-plane.env}"
TARGET_DIR="${CONTROL_PLANE_TARGET_DIR:-/opt/control-panel-container}"
# shellcheck source=./lib.sh
source "$ROOT_DIR/deploy/bootstrap/lib.sh"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "control-plane env file not found: $ENV_FILE"
  exit 1
fi

if ! command -v docker >/dev/null 2>&1; then
  echo "docker is required on control-plane host"
  exit 1
fi

apt-get update >/dev/null
apt-get install -y docker-compose-v2 >/dev/null || apt-get install -y docker-compose-plugin >/dev/null || true
mkdir -p "$TARGET_DIR"
find "$TARGET_DIR" -mindepth 1 -maxdepth 1 \
  ! -name runtime \
  -exec rm -rf {} +
cp -a "$ROOT_DIR/." "$TARGET_DIR/"

cp "$ENV_FILE" "$TARGET_DIR/.env"

cd "$TARGET_DIR"
docker compose up -d --build

docker compose ps
