import json

from fastapi.testclient import TestClient

from app.api import deps
from app.main import app


class DummyRelayRepo:
    def is_port_reachable(self, timeout: int = 2) -> bool:
        return True

    def get_remote_service_status(self) -> str:
        return "active"


def test_update_frontend_config_updates_live_runtime_and_restarts(tmp_path, monkeypatch) -> None:
    config_path = tmp_path / "config.json"
    access_log_path = tmp_path / "access.log"
    meta_path = tmp_path / "clients-meta.json"
    xray_path = tmp_path / "xray"
    xray_path.write_text("#!/usr/bin/env bash\necho 'Public key: derived-pub'\n")
    xray_path.chmod(0o755)

    config_path.write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "frontend-in",
                        "port": 9444,
                        "settings": {"clients": [{"id": "client-1", "email": "alpha"}]},
                        "streamSettings": {
                            "realitySettings": {
                                "privateKey": "priv",
                                "serverNames": ["example.com"],
                                "target": "example.com:443",
                                "shortIds": ["aaaaaaaaaaaaaaaa"],
                                "settings": {"fingerprint": "chrome", "spiderX": "/"},
                            }
                        },
                    }
                ],
                "outbounds": [
                    {
                        "tag": "to-relay",
                        "settings": {
                            "vnext": [
                                {
                                    "address": "203.0.113.10",
                                    "port": 9443,
                                    "users": [{"id": "relay-uuid"}],
                                }
                            ]
                        },
                    }
                ],
            }
        )
        + "\n"
    )
    meta_path.write_text(json.dumps({"clients": {"client-1": {"name": "alpha"}}}) + "\n")
    access_log_path.write_text("")

    monkeypatch.setenv("XRAY_FRONTEND_CONFIG_PATH", str(config_path))
    monkeypatch.setenv("XRAY_FRONTEND_ACCESS_LOG_PATH", str(access_log_path))
    monkeypatch.setenv("XRAY_FRONTEND_SERVICE_NAME", "xray-frontend")
    monkeypatch.setenv("XRAY_FRONTEND_USE_NSENTER", "1")
    monkeypatch.setenv("XRAY_BINARY_PATH", str(xray_path))
    monkeypatch.setenv("XRAY_CLIENT_META_PATH", str(meta_path))
    monkeypatch.setenv("XRAY_RELAY_HOST", "203.0.113.10")
    monkeypatch.setenv("XRAY_RELAY_PORT", "9443")
    monkeypatch.setenv("XRAY_RELAY_SERVICE_NAME", "xray-relay")
    monkeypatch.setenv("XRAY_RELAY_SSH_KEY_PATH", str(tmp_path / "dummy.key"))
    monkeypatch.setenv("XRAY_RELAY_SSH_USER", "deploy")
    monkeypatch.setenv("XRAY_EXPECTED_EGRESS_IP", "203.0.113.10")
    monkeypatch.setenv("XRAY_ADMIN_USER", "admin")
    monkeypatch.setenv("XRAY_ADMIN_PASSWORD", "change-me")
    deps.get_settings.cache_clear()

    commands: list[list[str]] = []

    def fake_run(cmd, check=False, capture_output=False, text=False, **kwargs):
        commands.append(cmd)

        class Result:
            def __init__(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> None:
                self.stdout = stdout
                self.stderr = stderr
                self.returncode = returncode

        if cmd[:2] == [str(xray_path), "x25519"]:
            return Result(stdout="Public key: derived-pub\n")
        if cmd[:2] == ["nsenter", "-t"]:
            return Result(stdout="active\n")
        raise AssertionError(f"unexpected subprocess.run command: {cmd}")

    monkeypatch.setattr("app.repos.xray_frontend_repo.subprocess.run", fake_run)
    monkeypatch.setattr("app.api.deps.RelayNodeRepo", lambda **kwargs: DummyRelayRepo())

    client = TestClient(app)
    response = client.put(
        "/api/xray-frontend/config/frontend",
        auth=("admin", "change-me"),
        json={
            "port": 9555,
            "server_name": "updated.example.com",
            "fingerprint": "firefox",
            "target": "updated.example.com:8443",
            "spider_x": "/health",
            "short_ids": ["1111111111111111", "2222222222222222"],
            "relay_host": "198.51.100.20",
            "relay_port": 9556,
        },
    )

    assert response.status_code == 200
    payload = response.json()
    live_config = json.loads(config_path.read_text())
    inbound = next(item for item in live_config["inbounds"] if item["tag"] == "frontend-in")
    outbound = next(item for item in live_config["outbounds"] if item["tag"] == "to-relay")
    reality = inbound["streamSettings"]["realitySettings"]
    relay = outbound["settings"]["vnext"][0]

    assert payload["port"] == 9555
    assert payload["server_name"] == "updated.example.com"
    assert inbound["port"] == 9555
    assert reality["target"] == "updated.example.com:8443"
    assert reality["dest"] == "updated.example.com:8443"
    assert reality["serverNames"] == ["updated.example.com"]
    assert reality["fingerprint"] == "firefox"
    assert reality["spiderX"] == "/health"
    assert reality["settings"]["fingerprint"] == "firefox"
    assert reality["settings"]["spiderX"] == "/health"
    assert reality["shortIds"] == ["1111111111111111", "2222222222222222"]
    assert relay["address"] == "198.51.100.20"
    assert relay["port"] == 9556
    assert any(cmd[-2:] == ["restart", "xray-frontend"] for cmd in commands)
