#!/usr/bin/env python3
"""Restore client entries from clients-meta.json into config.json after template render.

Usage:
    python3 restore_clients.py <config_path> <meta_path>

Defaults:
    config_path = /opt/xray-frontend/config.json
    meta_path   = /opt/xray-frontend/clients-meta.json
"""
import json
import sys
from pathlib import Path


def restore_clients(config_path: Path, meta_path: Path) -> int:
    """Merge clients from meta into config. Returns number of clients restored."""
    if not meta_path.exists():
        return 0
    raw = meta_path.read_text().strip()
    if not raw:
        return 0
    meta = json.loads(raw)
    clients_meta = meta.get("clients", {})
    if not clients_meta:
        return 0

    config = json.loads(config_path.read_text())
    inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
    reality = inbound["streamSettings"]["realitySettings"]
    existing_ids = {c["id"] for c in inbound["settings"].get("clients", [])}

    restored = 0
    for cid, cmeta in clients_meta.items():
        if cid in existing_ids:
            continue
        inbound["settings"].setdefault("clients", []).append({
            "id": cid,
            "email": cmeta.get("name", cid),
        })
        short_id = cmeta.get("short_id", "")
        if short_id and short_id not in reality.get("shortIds", []):
            reality.setdefault("shortIds", []).append(short_id)
        restored += 1

    if restored:
        config_path.write_text(json.dumps(config, indent=2))
    return restored


if __name__ == "__main__":
    config_p = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("/opt/xray-frontend/config.json")
    meta_p = Path(sys.argv[2]) if len(sys.argv) > 2 else Path("/opt/xray-frontend/clients-meta.json")
    count = restore_clients(config_p, meta_p)
    if count:
        print(f"Restored {count} client(s) from clients-meta.json")
