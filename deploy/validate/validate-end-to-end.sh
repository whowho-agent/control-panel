#!/usr/bin/env bash
set -euo pipefail

CONTROL_PLANE_URL="${CONTROL_PLANE_URL:-http://127.0.0.1:8000/health}"
EXPECTED_EGRESS_IP="${EXPECTED_EGRESS_IP:-}"

curl -fsS "$CONTROL_PLANE_URL" >/dev/null

echo 'control-plane reachable'
if [[ -n "$EXPECTED_EGRESS_IP" ]]; then
  echo "expected egress ip: $EXPECTED_EGRESS_IP"
fi
