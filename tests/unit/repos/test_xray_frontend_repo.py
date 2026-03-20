import json
from pathlib import Path

from app.repos.xray_frontend_repo import XrayFrontendRepo


def test_get_frontend_config_returns_runtime_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    access_log_path = tmp_path / "access.log"
    config_path.write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "frontend-in",
                        "port": 9444,
                        "streamSettings": {
                            "realitySettings": {
                                "privateKey": "priv",
                                "serverNames": ["mitigator.ru"],
                                "target": "mitigator.ru:443",
                                "shortIds": ["sid-a"],
                                "settings": {"fingerprint": "firefox", "spiderX": "/"},
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
                                    "address": "72.56.109.197",
                                    "port": 9443,
                                    "users": [{"id": "relay-uuid"}],
                                }
                            ]
                        },
                    }
                ],
            }
        )
    )
    xray_path = tmp_path / "xray"
    xray_path.write_text("#!/usr/bin/env bash\necho 'Public key: derived-pub'\n")
    xray_path.chmod(0o755)

    repo = XrayFrontendRepo(
        config_path=str(config_path),
        access_log_path=str(access_log_path),
        service_name="xray-frontend",
        xray_binary_path=str(xray_path),
        use_nsenter=False,
    )

    result = repo.get_frontend_config()

    assert result.port == 9444
    assert result.server_name == "mitigator.ru"
    assert result.public_key == "derived-pub"
    assert result.relay_host == "72.56.109.197"
    assert result.relay_port == 9443
    assert result.relay_uuid == "relay-uuid"


def test_get_relay_config_from_frontend_returns_outbound_values(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    access_log_path = tmp_path / "access.log"
    config_path.write_text(
        json.dumps(
            {
                "inbounds": [
                    {
                        "tag": "frontend-in",
                        "port": 9444,
                        "streamSettings": {
                            "realitySettings": {
                                "privateKey": "priv",
                                "serverNames": ["mitigator.ru"],
                                "target": "mitigator.ru:443",
                                "shortIds": ["sid-a"],
                                "settings": {"fingerprint": "firefox", "spiderX": "/"},
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
                                    "port": 9777,
                                    "users": [{"id": "relay-new"}],
                                }
                            ]
                        },
                    }
                ],
            }
        )
    )
    xray_path = tmp_path / "xray"
    xray_path.write_text("#!/usr/bin/env bash\necho 'Public key: derived-pub'\n")
    xray_path.chmod(0o755)

    repo = XrayFrontendRepo(
        config_path=str(config_path),
        access_log_path=str(access_log_path),
        service_name="xray-frontend",
        xray_binary_path=str(xray_path),
        use_nsenter=False,
    )

    result = repo.get_relay_config_from_frontend()

    assert result.host == "203.0.113.10"
    assert result.port == 9777
    assert result.uuid == "relay-new"
