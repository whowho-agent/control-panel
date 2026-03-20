#!/usr/bin/env bash
set -euo pipefail

require_env_file() {
  local env_file="$1"
  if [[ ! -f "$env_file" ]]; then
    echo "env file not found: $env_file"
    exit 1
  fi
}

install_xray_binary() {
  local install_dir="$1"
  local version="${XRAY_VERSION:-1.8.24}"
  local arch="linux-64"
  local url="https://github.com/XTLS/Xray-core/releases/download/v${version}/Xray-${arch}.zip"
  local tmp_dir
  tmp_dir="$(mktemp -d)"
  trap 'rm -rf "$tmp_dir"' RETURN

  apt-get update >/dev/null
  apt-get install -y curl unzip >/dev/null
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
