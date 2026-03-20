#!/usr/bin/env bash
set -euo pipefail

systemctl is-active xray-frontend
ss -lntup | grep ':9444'
test -f /opt/xray-frontend/config.json

echo 'gateway validation ok'
