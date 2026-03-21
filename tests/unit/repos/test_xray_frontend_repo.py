import json
from pathlib import Path
from unittest.mock import patch

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


def test_validate_config_reports_preflight_error(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    access_log_path = tmp_path / "access.log"
    xray_path = tmp_path / "xray"
    xray_path.write_text("#!/usr/bin/env bash\nexit 0\n")
    xray_path.chmod(0o755)

    repo = XrayFrontendRepo(
        config_path=str(config_path),
        access_log_path=str(access_log_path),
        service_name="xray-frontend",
        xray_binary_path=str(xray_path),
        use_nsenter=False,
    )

    with patch("app.repos.xray_frontend_repo.subprocess.run") as run:
        run.return_value.returncode = 23
        run.return_value.stdout = ""
        run.return_value.stderr = "failed to parse candidate config"

        result = repo.validate_config({"inbounds": [], "outbounds": []})

    assert result.preflight_ok is False
    assert result.status == "validation-failed"
    assert "failed to parse candidate config" in result.message


def test_apply_config_rolls_back_when_restart_fails(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    access_log_path = tmp_path / "access.log"
    xray_path = tmp_path / "xray"
    xray_path.write_text("#!/usr/bin/env bash\nexit 0\n")
    xray_path.chmod(0o755)
    previous = {"inbounds": [{"tag": "frontend-in", "port": 9444, "streamSettings": {"realitySettings": {}}}], "outbounds": []}
    config_path.write_text(json.dumps(previous) + "\n")

    repo = XrayFrontendRepo(
        config_path=str(config_path),
        access_log_path=str(access_log_path),
        service_name="xray-frontend",
        xray_binary_path=str(xray_path),
        use_nsenter=False,
    )

    with patch.object(repo, "validate_config_text") as validate, patch.object(repo, "restart_frontend") as restart:
        from app.domain.xray_frontend import FrontendApplyResult
        validate.return_value = FrontendApplyResult(True, False, False, "validated", "ok")
        restart.side_effect = [
            FrontendApplyResult(True, True, False, "not-ready", "restart failed"),
            FrontendApplyResult(True, True, True, "ready", "restored"),
        ]

        result = repo.apply_config({"inbounds": [], "outbounds": []})

    assert result.ready is False
    assert result.rollback_performed is True
    assert result.status == "rollback-restored"
    assert json.loads(config_path.read_text()) == previous


def test_systemctl_command_uses_nsenter_when_enabled(tmp_path: Path) -> None:
    repo = XrayFrontendRepo(
        config_path=str(tmp_path / "config.json"),
        access_log_path=str(tmp_path / "access.log"),
        service_name="xray-frontend",
        xray_binary_path=str(tmp_path / "xray"),
        use_nsenter=True,
    )

    command = repo._systemctl_command("restart")

    assert command == [
        "nsenter",
        "-t",
        "1",
        "-m",
        "-u",
        "-i",
        "-n",
        "-p",
        "systemctl",
        "restart",
        "xray-frontend",
    ]


def test_read_config_tolerates_literal_backslash_n_suffix(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    access_log_path = tmp_path / "access.log"
    xray_path = tmp_path / "xray"
    xray_path.write_text("#!/usr/bin/env bash\necho 'Public key: derived-pub'\n")
    xray_path.chmod(0o755)
    config_path.write_text('{"inbounds": [], "outbounds": []}\\n')

    repo = XrayFrontendRepo(
        config_path=str(config_path),
        access_log_path=str(access_log_path),
        service_name="xray-frontend",
        xray_binary_path=str(xray_path),
        use_nsenter=False,
    )

    assert repo.read_config() == {"inbounds": [], "outbounds": []}
