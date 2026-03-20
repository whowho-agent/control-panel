#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
ENV_DIR="$ROOT_DIR/deploy/env"
GATEWAY_ENV="$ENV_DIR/gateway.env"
EGRESS_ENV="$ENV_DIR/egress.env"
CONTROL_ENV="$ENV_DIR/control-plane.env"

mkdir -p "$ENV_DIR"

if ! command -v uuidgen >/dev/null 2>&1; then
  sudo apt-get update >/dev/null
  sudo apt-get install -y uuid-runtime >/dev/null
fi

if ! command -v openssl >/dev/null 2>&1; then
  sudo apt-get update >/dev/null
  sudo apt-get install -y openssl >/dev/null
fi

RELAY_UUID="$(uuidgen | tr 'A-Z' 'a-z')"
ADMIN_PASSWORD="$(openssl rand -base64 24 | tr -d '\n')"

if command -v /opt/xray-frontend/xray >/dev/null 2>&1; then
  XRAY_BIN="/opt/xray-frontend/xray"
elif command -v xray >/dev/null 2>&1; then
  XRAY_BIN="$(command -v xray)"
else
  XRAY_BIN=""
fi

if [[ -n "$XRAY_BIN" ]]; then
  KEY_OUTPUT="$($XRAY_BIN x25519)"
  REALITY_PRIVATE_KEY="$(printf '%s\n' "$KEY_OUTPUT" | awk -F': ' '/Private key:/ {print $2}')"
  REALITY_PUBLIC_KEY="$(printf '%s\n' "$KEY_OUTPUT" | awk -F': ' '/Public key:/ {print $2}')"
else
  REALITY_PRIVATE_KEY="replace-me"
  REALITY_PUBLIC_KEY="replace-me"
fi

if [[ ! -f "$GATEWAY_ENV" ]]; then
  cp "$ENV_DIR/gateway.env.example" "$GATEWAY_ENV"
fi
if [[ ! -f "$EGRESS_ENV" ]]; then
  cp "$ENV_DIR/egress.env.example" "$EGRESS_ENV"
fi
if [[ ! -f "$CONTROL_ENV" ]]; then
  cp "$ENV_DIR/control-plane.env.example" "$CONTROL_ENV"
fi

python3 - <<PY
from pathlib import Path

def upsert(path: Path, mapping: dict[str, str]) -> None:
    lines = path.read_text().splitlines() if path.exists() else []
    data = {}
    for line in lines:
        if '=' in line and not line.strip().startswith('#'):
            key, value = line.split('=', 1)
            data[key] = value
    for key, value in mapping.items():
        data[key] = value
    ordered = [f"{key}={value}" for key, value in data.items()]
    path.write_text("\n".join(ordered) + "\n")

upsert(Path("$GATEWAY_ENV"), {
    "XRAY_FRONTEND_REALITY_PRIVATE_KEY": "$REALITY_PRIVATE_KEY",
    "XRAY_RELAY_UUID": "$RELAY_UUID",
})
upsert(Path("$EGRESS_ENV"), {
    "XRAY_RELAY_UUID": "$RELAY_UUID",
})
upsert(Path("$CONTROL_ENV"), {
    "XRAY_RELAY_UUID": "$RELAY_UUID",
    "XRAY_ADMIN_PASSWORD": "$ADMIN_PASSWORD",
})
PY

echo "Generated/updated env files:"
echo "- $GATEWAY_ENV"
echo "- $EGRESS_ENV"
echo "- $CONTROL_ENV"
echo
echo "Relay UUID: $RELAY_UUID"
echo "Admin password: $ADMIN_PASSWORD"
echo "Reality private key: $REALITY_PRIVATE_KEY"
echo "Reality public key: $REALITY_PUBLIC_KEY"
