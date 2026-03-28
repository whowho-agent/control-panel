import json
import logging
import re
import subprocess
import tempfile
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.domain.xray_config import XrayConfigAccessor
from app.domain.xray_frontend import FrontendApplyResult, FrontendConfigResult, RelayConfigResult

logger = logging.getLogger(__name__)


class XrayFrontendRepo:
    def __init__(
        self,
        config_path: str,
        access_log_path: str,
        service_name: str,
        xray_binary_path: str,
        use_nsenter: bool = False,
    ) -> None:
        self.config_path = Path(config_path)
        self.access_log_path = Path(access_log_path)
        self.service_name = service_name
        self.xray_binary_path = xray_binary_path
        self.use_nsenter = use_nsenter

    def read_config(self) -> XrayConfigAccessor:
        return XrayConfigAccessor(self._load_json_file(self.config_path))

    def write_config(self, config: XrayConfigAccessor) -> None:
        raw = config.to_dict()
        self._ensure_runtime_files(raw)
        self.config_path.write_text(json.dumps(raw, indent=2) + "\n")

    def apply_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        logger.info("apply_config: start")
        previous_config = self.config_path.read_text() if self.config_path.exists() else ""
        raw = config.to_dict()
        rendered = json.dumps(raw, indent=2) + "\n"
        self._ensure_runtime_files(raw)
        validation = self.validate_config_text(rendered)
        if not validation.preflight_ok:
            logger.warning("apply_config: validation failed — %s", validation.message)
            return validation

        self.config_path.write_text(rendered)
        restart_result = self.restart_frontend()
        if restart_result.ready:
            logger.info("apply_config: done, service ready")
            return restart_result

        logger.error("apply_config: restart failed — %s, attempting rollback", restart_result.message)
        rollback_performed = False
        if previous_config:
            self.config_path.write_text(previous_config)
            rollback_result = self.restart_frontend()
            rollback_performed = rollback_result.ready
            logger.info("apply_config: rollback %s", "restored" if rollback_performed else "also failed")

        return FrontendApplyResult(
            preflight_ok=True,
            restarted=restart_result.restarted,
            ready=False,
            status="rollback-restored" if rollback_performed else "restart-failed",
            message=restart_result.message,
            rollback_performed=rollback_performed,
        )

    def validate_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        return self.validate_config_text(json.dumps(config.to_dict(), indent=2) + "\n")

    def validate_config_text(self, config_text: str) -> FrontendApplyResult:
        try:
            with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as tmp:
                tmp.write(config_text)
                tmp_path = Path(tmp.name)
            result = subprocess.run(
                [self.xray_binary_path, "run", "-test", "-config", str(tmp_path)],
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return FrontendApplyResult(
                preflight_ok=False,
                restarted=False,
                ready=False,
                status="validator-missing",
                message=f"Xray validator not found at {self.xray_binary_path}",
            )
        finally:
            if 'tmp_path' in locals() and tmp_path.exists():
                tmp_path.unlink()

        stderr = (result.stderr or "").strip()
        stdout = (result.stdout or "").strip()
        if result.returncode == 0:
            return FrontendApplyResult(
                preflight_ok=True,
                restarted=False,
                ready=False,
                status="validated",
                message="Config validation passed",
            )
        return FrontendApplyResult(
            preflight_ok=False,
            restarted=False,
            ready=False,
            status="validation-failed",
            message=stderr or stdout or "Xray rejected the candidate config",
        )

    def get_frontend_config(self) -> FrontendConfigResult:
        config = self.read_config()
        inbound = config.frontend_inbound()
        relay = config.relay_outbound()["settings"]["vnext"][0]
        reality = inbound["streamSettings"]["realitySettings"]
        settings = reality.get("settings", {})
        server_names = reality.get("serverNames") or []
        return FrontendConfigResult(
            port=inbound["port"],
            server_name=(server_names[0] if server_names else reality.get("serverName", "")),
            public_key=self.derive_public_key(reality.get("privateKey", "")),
            private_key=reality.get("privateKey", ""),
            fingerprint=reality.get("fingerprint", settings.get("fingerprint", "firefox")),
            short_ids=reality.get("shortIds", []),
            spider_x=reality.get("spiderX", settings.get("spiderX", "/")),
            target=reality.get("target", reality.get("dest", "")),
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

    def restart_frontend(self) -> FrontendApplyResult:
        logger.info("restart_frontend: sending systemctl restart %s", self.service_name)
        try:
            if self.config_path.exists():
                self._ensure_runtime_files(self.read_config().to_dict())
            restart = subprocess.run(
                self._systemctl_command("restart"),
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            return FrontendApplyResult(
                preflight_ok=True,
                restarted=False,
                ready=False,
                status="systemctl-missing",
                message="systemctl is not available in this runtime",
            )
        if restart.returncode != 0:
            msg = (restart.stderr or restart.stdout or "systemctl restart failed").strip()
            logger.error("restart_frontend: failed — %s", msg)
            return FrontendApplyResult(
                preflight_ok=True,
                restarted=False,
                ready=False,
                status="restart-failed",
                message=msg,
            )

        readiness = self.wait_until_ready()
        logger.info("restart_frontend: ready=%s status=%s", readiness[0], readiness[1])
        return FrontendApplyResult(
            preflight_ok=True,
            restarted=True,
            ready=readiness[0],
            status=readiness[1],
            message=readiness[2],
        )

    def wait_until_ready(self, attempts: int = 5, delay_seconds: float = 0.4) -> tuple[bool, str, str]:
        last_status = "unknown"
        for _ in range(attempts):
            last_status = self.get_frontend_service_status()
            if last_status == "active":
                return True, "ready", "Frontend service is active"
            time.sleep(delay_seconds)
        return False, "not-ready", f"Frontend service did not become active after restart (last status: {last_status})"

    def get_frontend_service_status(self) -> str:
        try:
            result = subprocess.run(
                self._systemctl_command("is-active"),
                check=False,
                capture_output=True,
                text=True,
                timeout=30,
            )
            status = result.stdout.strip() or result.stderr.strip() or "unknown"
            if status:
                return status
        except FileNotFoundError:
            pass
        if self.config_path.exists() and Path(self.xray_binary_path).exists():
            return "configured"
        return "unknown"

    def get_frontend_readiness(self) -> FrontendApplyResult:
        status = self.get_frontend_service_status()
        ready = status == "active"
        message = "Frontend service is ready" if ready else f"Frontend service is not ready (status: {status})"
        return FrontendApplyResult(
            preflight_ok=True,
            restarted=False,
            ready=ready,
            status="ready" if ready else status,
            message=message,
        )

    def derive_public_key(self, private_key: str) -> str:
        if not private_key:
            return ""
        result = subprocess.run(
            [self.xray_binary_path, "x25519", "-i", private_key],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
        )
        for line in result.stdout.splitlines():
            if line.startswith("Password:"):
                return line.split(":", 1)[1].strip()
            if line.startswith("Public key:"):
                return line.split(":", 1)[1].strip()
        return ""

    def parse_activity(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not self.access_log_path.exists():
            return result
        line_re = re.compile(
            r"^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}(?:\.\d+)?) "
            r"from (?:(?:tcp|udp):)?(?P<ip>[\d.]+):\d+ accepted .*? \[(?P<inbound>[^\]]+) ->"
        )
        email_re = re.compile(r"email:\s+(\S+)")
        lines = self.access_log_path.read_text(errors="ignore").splitlines()[-2000:]
        for line in lines:
            match = line_re.search(line)
            if not match or match.group("inbound") != "frontend-in":
                continue
            ts = match.group("ts")
            fmt = "%Y/%m/%d %H:%M:%S.%f" if "." in ts else "%Y/%m/%d %H:%M:%S"
            seen_at = datetime.strptime(ts, fmt).replace(tzinfo=timezone.utc)
            ip = match.group("ip")
            em = email_re.search(line)
            email = em.group(1) if em else ""
            key = email if email else ip
            previous = result.get(key)
            if not previous or seen_at > previous["last_seen_dt"]:
                result[key] = {
                    "last_seen_dt": seen_at,
                    "last_seen": seen_at.isoformat().replace("+00:00", "Z"),
                    "source_ip": ip,
                    "email": email,
                }
        return result

    def read_access_log_lines(self, tail: int = 5000) -> list[str]:
        if not self.access_log_path.exists():
            return []
        return self.access_log_path.read_text(errors="ignore").splitlines()[-tail:]

    def _systemctl_command(self, action: str) -> list[str]:
        if self.use_nsenter:
            return [
                "nsenter",
                "-t",
                "1",
                "-m",
                "-u",
                "-i",
                "-n",
                "-p",
                "systemctl",
                action,
                self.service_name,
            ]
        return ["systemctl", action, self.service_name]

    def _load_json_file(self, path: Path) -> dict:
        raw = path.read_text()
        if raw.endswith("\\n"):
            raw = raw[:-2] + "\n"
        return json.loads(raw)

    def _ensure_runtime_files(self, config: dict) -> None:
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.access_log_path.parent.mkdir(parents=True, exist_ok=True)
        self.access_log_path.touch(exist_ok=True)
        error_log = config.get("log", {}).get("error")
        if error_log:
            Path(error_log).parent.mkdir(parents=True, exist_ok=True)
            Path(error_log).touch(exist_ok=True)
