import json
import subprocess
from pathlib import Path

from app.domain.xray_frontend import FrontendConfigResult, RelayConfigResult


class XrayFrontendRepo:
    def __init__(self, config_path: str, access_log_path: str, service_name: str, xray_binary_path: str) -> None:
        self.config_path = Path(config_path)
        self.access_log_path = Path(access_log_path)
        self.service_name = service_name
        self.xray_binary_path = xray_binary_path

    def read_config(self) -> dict:
        return json.loads(self.config_path.read_text())

    def write_config(self, config: dict) -> None:
        self.config_path.write_text(json.dumps(config, indent=2) + "\n")

    def get_frontend_config(self) -> FrontendConfigResult:
        config = self.read_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        outbound = next(item for item in config["outbounds"] if item.get("tag") == "to-relay")
        reality = inbound["streamSettings"]["realitySettings"]
        relay = outbound["settings"]["vnext"][0]
        return FrontendConfigResult(
            port=inbound["port"],
            server_name=(reality.get("serverNames") or [""])[0],
            public_key=self.derive_public_key(reality.get("privateKey", "")),
            private_key=reality.get("privateKey", ""),
            fingerprint=reality.get("settings", {}).get("fingerprint", "firefox"),
            short_ids=reality.get("shortIds", []),
            spider_x=reality.get("settings", {}).get("spiderX", "/"),
            target=reality.get("target", ""),
            relay_host=relay["address"],
            relay_port=relay["port"],
            relay_uuid=relay["users"][0]["id"],
        )

    def get_relay_config_from_frontend(self) -> RelayConfigResult:
        frontend = self.get_frontend_config()
        return RelayConfigResult(
            host=frontend.relay_host,
            port=frontend.relay_port,
            uuid=frontend.relay_uuid,
        )

    def restart_frontend(self) -> None:
        try:
            subprocess.run(["systemctl", "restart", self.service_name], check=True, capture_output=True, text=True)
        except FileNotFoundError:
            return

    def get_frontend_service_status(self) -> str:
        try:
            result = subprocess.run(["systemctl", "is-active", self.service_name], check=False, capture_output=True, text=True)
        except FileNotFoundError:
            return "unknown"
        return result.stdout.strip() or result.stderr.strip() or "unknown"

    def derive_public_key(self, private_key: str) -> str:
        if not private_key:
            return ""
        result = subprocess.run(
            [self.xray_binary_path, "x25519", "-i", private_key],
            check=True,
            capture_output=True,
            text=True,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Password:"):
                return line.split(":", 1)[1].strip()
            if line.startswith("Public key:"):
                return line.split(":", 1)[1].strip()
        return ""
