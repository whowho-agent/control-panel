#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000/health}"
EXPECTED_EGRESS_IP="${EXPECTED_EGRESS_IP:-}"
EGRESS_HOST="${EGRESS_HOST:-}"
EGRESS_SSH_USER="${EGRESS_SSH_USER:-deploy}"
EGRESS_SSH_KEY_PATH="${EGRESS_SSH_KEY_PATH:-}"
EGRESS_SSH_PORT="${EGRESS_SSH_PORT:-22}"

curl -fsS "$CONTROL_PLANE_URL" >/dev/null
echo 'control-plane reachable'

if [[ -n "$EGRESS_HOST" && -n "$EGRESS_SSH_KEY_PATH" ]]; then
  OBSERVED_IP="$(ssh -i "$EGRESS_SSH_KEY_PATH" -p "$EGRESS_SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new "$EGRESS_SSH_USER@$EGRESS_HOST" 'curl -4fsS https://api.ipify.org' 2>/dev/null || true)"
  if [[ -z "$OBSERVED_IP" ]]; then
    echo 'egress probe failed'
    exit 1
  fi
  echo "observed egress ip: $OBSERVED_IP"
  if [[ -n "$EXPECTED_EGRESS_IP" && "$OBSERVED_IP" != "$EXPECTED_EGRESS_IP" ]]; then
    echo "unexpected egress ip: expected $EXPECTED_EGRESS_IP got $OBSERVED_IP"
    exit 1
  fi
fi

if [[ -n "$EXPECTED_EGRESS_IP" ]]; then
  echo "expected egress ip: $EXPECTED_EGRESS_IP"
fi
