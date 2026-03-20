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

mkdir -p "$TARGET_DIR"
rsync -az --delete \
  --exclude '.git' --exclude 'memory' --exclude 'keys' --exclude 'secrets' --exclude '.openclaw' \
  "$ROOT_DIR/" "$TARGET_DIR/"

cp "$ENV_FILE" "$TARGET_DIR/.env"
mkdir -p "$TARGET_DIR/runtime/frontend" "$TARGET_DIR/runtime/ssh"

echo "Place runtime frontend files into: $TARGET_DIR/runtime/frontend"
echo "Place relay SSH key into:        $TARGET_DIR/runtime/ssh/relay_ssh_key"

echo "Then run:"
echo "  cd $TARGET_DIR && docker compose up -d --build"
