#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -f .env ]]; then
  echo ".env not found. Copy .env.example to .env and edit it first."
  exit 1
fi

mkdir -p runtime/frontend runtime/ssh

docker compose up -d --build

echo
echo "control-plane started"
docker compose ps
