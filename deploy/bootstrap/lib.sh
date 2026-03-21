#!/usr/bin/env bash
set -euo pipefail

APT_LOCK_WAIT_TIMEOUT="${APT_LOCK_WAIT_TIMEOUT:-600}"
APT_LOCK_WAIT_INTERVAL="${APT_LOCK_WAIT_INTERVAL:-5}"
TCP_WAIT_TIMEOUT="${TCP_WAIT_TIMEOUT:-90}"
TCP_WAIT_INTERVAL="${TCP_WAIT_INTERVAL:-2}"

log_phase() {
  local phase="$1"
  echo "==> ${phase}"
}

require_env_file() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    echo "env file not found: $env_file"
    exit 1
  fi
}

load_env_file() {
  local env_file="$1"
  require_env_file "$env_file"
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
}

require_env_vars() {
  local var_name
  for var_name in "$@"; do
    if [[ -z "${!var_name:-}" ]]; then
      echo "required env var is missing: ${var_name}" >&2
      exit 1
    fi
  done
}

wait_for_apt_locks() {
  local timeout="${1:-${APT_LOCK_WAIT_TIMEOUT:-600}}"
  local interval="${2:-${APT_LOCK_WAIT_INTERVAL:-5}}"
  [[ -n "$timeout" ]] || timeout=600
  [[ -n "$interval" ]] || interval=5
  local waited=0
  local -a lock_paths=(
    /var/lib/dpkg/lock-frontend
    /var/lib/dpkg/lock
    /var/lib/apt/lists/lock
    /var/cache/apt/archives/lock
  )

  while (( waited < timeout )); do
    local busy=0
    local service_busy=0

    if command -v systemctl >/dev/null 2>&1; then
      for unit in apt-daily.service apt-daily-upgrade.service unattended-upgrades.service; do
        if systemctl is-active --quiet "$unit"; then
          service_busy=1
          break
        fi
      done
    fi

    if command -v fuser >/dev/null 2>&1; then
      for lock_path in "${lock_paths[@]}"; do
        if fuser "$lock_path" >/dev/null 2>&1; then
          busy=1
          break
        fi
      done
    elif pgrep -xfa "(apt|apt-get|dpkg|unattended-upgrade).*" >/dev/null 2>&1; then
      busy=1
    fi

    if (( busy == 0 && service_busy == 0 )); then
      return 0
    fi

    sleep "$interval"
    waited=$((waited + interval))
  done

  echo "timed out waiting for apt/dpkg locks or unattended-upgrades to finish after ${timeout}s" >&2
  return 1
}

apt_get_safe() {
  wait_for_apt_locks
  DEBIAN_FRONTEND=noninteractive apt-get -o DPkg::Lock::Timeout="$APT_LOCK_WAIT_TIMEOUT" "$@"
}

install_apt_packages() {
  apt_get_safe update >/dev/null
  apt_get_safe install -y "$@" >/dev/null
}

wait_for_tcp_endpoint() {
  local host="$1"
  local port="$2"
  local timeout="${3:-${TCP_WAIT_TIMEOUT:-90}}"
  local interval="${4:-${TCP_WAIT_INTERVAL:-2}}"
  [[ -n "$timeout" ]] || timeout=90
  [[ -n "$interval" ]] || interval=2
  local waited=0

  while (( waited < timeout )); do
    if python3 - "$host" "$port" <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
try:
    with socket.create_connection((host, port), timeout=2):
        pass
except OSError:
    raise SystemExit(1)
PY
    then
      return 0
    fi

    sleep "$interval"
    waited=$((waited + interval))
  done

  echo "timed out waiting for TCP endpoint ${host}:${port} after ${timeout}s" >&2
  return 1
}

install_xray_binary() {
  local install_dir="$1"
  local version="${XRAY_VERSION:-1.8.24}"
  local arch="linux-64"
  local url="https://github.com/XTLS/Xray-core/releases/download/v${version}/Xray-${arch}.zip"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' RETURN

  apt_get_safe update >/dev/null
  apt_get_safe install -y curl unzip >/dev/null
  install -d -m 755 "$install_dir"

  curl -fsSL "$url" -o "$tmp_dir/xray.zip"
  unzip -q "$tmp_dir/xray.zip" -d "$tmp_dir/xray"
  install -m 755 "$tmp_dir/xray/xray" "$install_dir/xray"
}

ensure_runtime_file() {
  local source_path="$1"
  local target_path="$2"
  if [[ -f "$source_path" ]]; then
    install -D -m 644 "$source_path" "$target_path"
  fi
}
