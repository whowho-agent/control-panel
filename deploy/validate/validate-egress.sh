#!/usr/bin/env bash
set -euo pipefail

systemctl is-active xray-relay
ss -lntup | grep ':9443'
test -f /opt/xray-relay/config.json

echo 'egress validation ok'
