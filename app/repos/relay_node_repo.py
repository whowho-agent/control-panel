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
            [
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
                f"sudo systemctl is-active {self.service_name}",
            ],
            check=False,
            capture_output=True,
            text=True,
        )
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        return "unknown"
