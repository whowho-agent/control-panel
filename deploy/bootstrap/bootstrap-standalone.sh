#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
DEPLOY_ENV_FILE="${1:-$ROOT_DIR/deploy/env/standalone.env}"
GATEWAY_ENV_FILE="${GATEWAY_ENV_FILE:-$ROOT_DIR/deploy/env/gateway.env}"
EGRESS_ENV_FILE="${EGRESS_ENV_FILE:-$ROOT_DIR/deploy/env/egress.env}"
REMOTE_BASE_DIR="${REMOTE_BASE_DIR:-/tmp/openclaw-xray-bootstrap}"
# shellcheck source=./lib.sh
source "$ROOT_DIR/deploy/bootstrap/lib.sh"

require_env_file "$DEPLOY_ENV_FILE"
require_env_file "$GATEWAY_ENV_FILE"
require_env_file "$EGRESS_ENV_FILE"

source "$DEPLOY_ENV_FILE"
source "$GATEWAY_ENV_FILE"
source "$EGRESS_ENV_FILE"

: "${EGRESS_HOST:?}"
: "${EGRESS_SSH_USER:?}"

EGRESS_SSH_PORT="${EGRESS_SSH_PORT:-22}"
EGRESS_SSH_KEY_PATH="${EGRESS_SSH_KEY_PATH:-}"
SSH_OPTS=(-p "$EGRESS_SSH_PORT" -o BatchMode=yes -o StrictHostKeyChecking=accept-new)
if [[ -n "$EGRESS_SSH_KEY_PATH" ]]; then
  SSH_OPTS+=( -i "$EGRESS_SSH_KEY_PATH" )
fi
REMOTE_TARGET="${EGRESS_SSH_USER}@${EGRESS_HOST}"

if [[ -z "${XRAY_RELAY_HOST:-}" ]]; then
  export XRAY_RELAY_HOST="$EGRESS_HOST"
fi
if [[ "$XRAY_RELAY_HOST" != "$EGRESS_HOST" ]]; then
  echo "warning: XRAY_RELAY_HOST ($XRAY_RELAY_HOST) differs from EGRESS_HOST ($EGRESS_HOST)" >&2
fi

TMP_GATEWAY_ENV="$(mktemp)"
trap 'rm -f "$TMP_GATEWAY_ENV"' EXIT
python3 - "$GATEWAY_ENV_FILE" "$TMP_GATEWAY_ENV" "$EGRESS_HOST" <<'PY'
from pathlib import Path
import sys
src, dst, egress_host = sys.argv[1:4]
lines = Path(src).read_text().splitlines()
out = []
updated = False
for line in lines:
    if line.startswith('XRAY_RELAY_HOST='):
        out.append(f'XRAY_RELAY_HOST={egress_host}')
        updated = True
    else:
        out.append(line)
if not updated:
    out.append(f'XRAY_RELAY_HOST={egress_host}')
Path(dst).write_text('\n'.join(out) + '\n')
PY

echo "==> checking SSH access to $REMOTE_TARGET"
ssh "${SSH_OPTS[@]}" "$REMOTE_TARGET" 'true'

echo "==> staging bootstrap files on $REMOTE_TARGET"
ssh "${SSH_OPTS[@]}" "$REMOTE_TARGET" "mkdir -p '$REMOTE_BASE_DIR/deploy/bootstrap' '$REMOTE_BASE_DIR/deploy/templates' '$REMOTE_BASE_DIR/deploy/env'"
scp "${SSH_OPTS[@]}" \
  "$ROOT_DIR/deploy/bootstrap/bootstrap-egress.sh" \
  "$ROOT_DIR/deploy/bootstrap/lib.sh" \
  "$ROOT_DIR/deploy/templates/xray-relay.config.json.template" \
  "$EGRESS_ENV_FILE" \
  "$REMOTE_TARGET:$REMOTE_BASE_DIR/"
ssh "${SSH_OPTS[@]}" "$REMOTE_TARGET" "install -m 644 '$REMOTE_BASE_DIR/egress.env' '$REMOTE_BASE_DIR/deploy/env/egress.env' && install -m 644 '$REMOTE_BASE_DIR/xray-relay.config.json.template' '$REMOTE_BASE_DIR/deploy/templates/xray-relay.config.json.template' && install -m 755 '$REMOTE_BASE_DIR/bootstrap-egress.sh' '$REMOTE_BASE_DIR/deploy/bootstrap/bootstrap-egress.sh' && install -m 644 '$REMOTE_BASE_DIR/lib.sh' '$REMOTE_BASE_DIR/deploy/bootstrap/lib.sh'"

echo "==> bootstrapping egress on $REMOTE_TARGET"
ssh -t "${SSH_OPTS[@]}" "$REMOTE_TARGET" "bash '$REMOTE_BASE_DIR/deploy/bootstrap/bootstrap-egress.sh' '$REMOTE_BASE_DIR/deploy/env/egress.env'"

echo "==> bootstrapping gateway locally"
bash "$ROOT_DIR/deploy/bootstrap/bootstrap-gateway.sh" "$TMP_GATEWAY_ENV"

echo "==> standalone bootstrap complete"
echo "gateway frontend -> relay host: $EGRESS_HOST"
