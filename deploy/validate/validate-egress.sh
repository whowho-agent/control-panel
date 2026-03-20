#!/usr/bin/env bash
set -euo pipefail

PORT="${XRAY_RELAY_PORT:-9443}"

systemctl is-active xray-relay
ss -lntup | grep -E ":${PORT}\b"
test -f /opt/xray-relay/config.json

echo 'egress validation ok'
