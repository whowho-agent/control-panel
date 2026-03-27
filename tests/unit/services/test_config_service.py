import pytest

from app.domain.xray_config import XrayConfigAccessor
from app.domain.xray_frontend import ControlPlaneError, FrontendApplyResult, FrontendConfigResult, RelayConfigResult
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand
from app.services.config_service import ConfigService


class FakeFrontendRepo:
    def __init__(self, config: dict) -> None:
        self.config = config
        self.restart_calls = 0
        self.apply_result = FrontendApplyResult(True, True, True, "ready", "ok")
        self.validate_result = FrontendApplyResult(True, False, False, "validated", "Config validation passed")

    def read_config(self) -> XrayConfigAccessor:
        return XrayConfigAccessor(self.config)

    def apply_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        self.config = config.to_dict()
        if self.apply_result.restarted:
            self.restart_calls += 1
        return self.apply_result

    def validate_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        return self.validate_result

    def get_frontend_config(self) -> FrontendConfigResult:
        inbound = next(item for item in self.config["inbounds"] if item["tag"] == "frontend-in")
        outbound = next(item for item in self.config["outbounds"] if item["tag"] == "to-relay")
        reality = inbound["streamSettings"]["realitySettings"]
        relay = outbound["settings"]["vnext"][0]
        return FrontendConfigResult(
            port=inbound["port"],
            server_name=reality["serverNames"][0],
            public_key="pub",
            private_key=reality["privateKey"],
            fingerprint=reality["settings"]["fingerprint"],
            short_ids=reality["shortIds"],
            spider_x=reality["settings"]["spiderX"],
            target=reality["target"],
            relay_host=relay["address"],
            relay_port=relay["port"],
            relay_uuid=relay["users"][0]["id"],
        )

    def get_relay_config_from_frontend(self) -> RelayConfigResult:
        fc = self.get_frontend_config()
        return RelayConfigResult(host=fc.relay_host, port=fc.relay_port, uuid=fc.relay_uuid)


def _base_config() -> dict:
    return {
        "inbounds": [
            {
                "tag": "frontend-in",
                "port": 9444,
                "settings": {"clients": []},
                "streamSettings": {
                    "realitySettings": {
                        "privateKey": "priv",
                        "serverNames": ["mitigator.ru"],
                        "target": "mitigator.ru:443",
                        "shortIds": ["aaaa"],
                        "settings": {"fingerprint": "firefox", "spiderX": "/"},
                    }
                },
            }
        ],
        "outbounds": [
            {
                "tag": "to-relay",
                "settings": {"vnext": [{"address": "1.2.3.4", "port": 9443, "users": [{"id": "relay-uuid"}]}]},
            }
        ],
    }


def build_service() -> tuple[ConfigService, FakeFrontendRepo]:
    repo = FakeFrontendRepo(config=_base_config())
    svc = ConfigService(frontend_repo=repo)
    return svc, repo


def test_get_frontend_returns_config() -> None:
    svc, _ = build_service()
    result = svc.get_frontend()
    assert result.port == 9444
    assert result.relay_host == "1.2.3.4"


def test_get_relay_returns_relay_config() -> None:
    svc, _ = build_service()
    result = svc.get_relay()
    assert result.host == "1.2.3.4"
    assert result.uuid == "relay-uuid"


def test_validate_frontend_no_restart() -> None:
    svc, repo = build_service()
    result = svc.validate_frontend(
        UpdateFrontendConfigCommand(
            port=9555,
            server_name="example.org",
            fingerprint="chrome",
            target="example.org:443",
            spider_x="/",
            short_ids=["bbbb"],
            relay_host="2.3.4.5",
            relay_port=9556,
        )
    )
    assert result.preflight_ok is True
    assert result.status == "validated"
    assert repo.restart_calls == 0


def test_update_frontend_applies_and_returns_new_config() -> None:
    svc, repo = build_service()
    result = svc.update_frontend(
        UpdateFrontendConfigCommand(
            port=9555,
            server_name="example.org",
            fingerprint="chrome",
            target="example.org:443",
            spider_x="/",
            short_ids=["bbbb"],
            relay_host="2.3.4.5",
            relay_port=9556,
        )
    )
    assert result.port == 9555
    assert result.server_name == "example.org"
    assert repo.restart_calls == 1


def test_update_frontend_raises_on_apply_failure() -> None:
    svc, repo = build_service()
    repo.apply_result = FrontendApplyResult(True, False, False, "restart-failed", "boom")
    with pytest.raises(ControlPlaneError, match="not applied"):
        svc.update_frontend(
            UpdateFrontendConfigCommand(
                port=9555,
                server_name="example.org",
                fingerprint="chrome",
                target="example.org:443",
                spider_x="/",
                short_ids=["bbbb"],
                relay_host="2.3.4.5",
                relay_port=9556,
            )
        )


def test_update_relay_updates_outbound() -> None:
    svc, repo = build_service()
    result = svc.update_relay(
        UpdateRelayConfigCommand(public_host="5.6.7.8", listen_port=9777, relay_uuid="new-uuid")
    )
    assert result.host == "5.6.7.8"
    assert result.port == 9777
    assert result.uuid == "new-uuid"
    assert repo.restart_calls == 1
