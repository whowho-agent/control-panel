import logging
import socket

import httpx

logger = logging.getLogger(__name__)


class RelayNodeRepo:
    def __init__(
        self,
        host: str,
        port: int,
        agent_url: str,
    ) -> None:
        self.host = host
        self.port = port
        self._agent_url = agent_url.rstrip("/")

    def is_port_reachable(self, timeout: int = 2) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                return True
        except OSError:
            return False

    def get_remote_service_status(self) -> str:
        try:
            r = httpx.get(f"{self._agent_url}/status", timeout=3.0)
            return r.json().get("service", "unknown")
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("get_remote_service_status: agent error — %s", exc)
            return "unknown"

    def probe_observed_public_ip(self) -> str:
        try:
            r = httpx.get(f"{self._agent_url}/status", timeout=3.0)
            return r.json().get("egress_ip", "")
        except (httpx.HTTPError, OSError) as exc:
            logger.warning("probe_observed_public_ip: agent error — %s", exc)
            return ""
