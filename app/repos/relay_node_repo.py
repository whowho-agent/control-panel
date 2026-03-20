import socket
import subprocess


class RelayNodeRepo:
    def __init__(self, host: str, port: int, service_name: str, ssh_key_path: str, ssh_user: str) -> None:
        self.host = host
        self.port = port
        self.service_name = service_name
        self.ssh_key_path = ssh_key_path
        self.ssh_user = ssh_user

    def is_port_reachable(self, timeout: int = 2) -> bool:
        try:
            with socket.create_connection((self.host, self.port), timeout=timeout):
                return True
        except OSError:
            return False

    def get_remote_service_status(self) -> str:
        result = subprocess.run(
            self._ssh_command(f"sudo systemctl is-active {self.service_name}"),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "unknown"

    def probe_observed_public_ip(self) -> str:
        result = subprocess.run(
            self._ssh_command("curl -4fsS https://api.ipify.org"),
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0:
            return result.stdout.strip()
        return ""

    def _ssh_command(self, remote_command: str) -> list[str]:
        return [
            "ssh",
            "-i",
            self.ssh_key_path,
            "-o",
            "BatchMode=yes",
            "-o",
            "ConnectTimeout=3",
            "-o",
            "StrictHostKeyChecking=accept-new",
            f"{self.ssh_user}@{self.host}",
            remote_command,
        ]
