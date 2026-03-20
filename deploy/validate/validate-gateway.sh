#!/usr/bin/env bash
set -euo pipefail

PORT="${XRAY_FRONTEND_PORT:-9444}"

systemctl is-active xray-frontend
ss -lntup | grep -E ":${PORT}\b"
test -f /opt/xray-frontend/config.json

echo 'gateway validation ok'
