from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.domain.transport_mode import TransportMode
from app.domain.xray_config import XrayConfigAccessor
from app.domain.xray_frontend import (
    CreateFrontendClientCommand,
    FrontendApplyResult,
    FrontendConfigResult,
    RelayConfigResult,
)
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand
from app.services.xray_frontend_service import XrayFrontendService


class FakeFrontendRepo:
    def __init__(self, config: dict, access_log_path: Path) -> None:
        self.config = config
        self.access_log_path = access_log_path
        self.restart_calls = 0
        self.apply_result = FrontendApplyResult(True, True, True, "ready", "Frontend service is active")
        self.validate_result = FrontendApplyResult(True, False, False, "validated", "Config validation passed")

    def read_config(self) -> XrayConfigAccessor:
        return XrayConfigAccessor(self.config)

    def write_config(self, config: XrayConfigAccessor) -> None:
        self.config = config.to_dict()

    def apply_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        self.config = config.to_dict()
        if self.apply_result.restarted:
            self.restart_calls += 1
        return self.apply_result

    def validate_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        self.config = config.to_dict()
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
        frontend = self.get_frontend_config()
        return RelayConfigResult(
            host=frontend.relay_host,
            port=frontend.relay_port,
            uuid=frontend.relay_uuid,
        )

    def parse_activity(self) -> dict:
        from app.repos.xray_frontend_repo import XrayFrontendRepo
        repo = XrayFrontendRepo.__new__(XrayFrontendRepo)
        repo.access_log_path = self.access_log_path
        return repo.parse_activity()

    def get_frontend_service_status(self) -> str:
        return "configured"

    def get_frontend_readiness(self) -> FrontendApplyResult:
        return FrontendApplyResult(True, False, True, "ready", "Frontend service is ready")


class FakeMetaRepo:
    def __init__(self, meta: dict) -> None:
        self.meta = meta

    def read(self) -> dict:
        return self.meta

    def write(self, meta: dict) -> None:
        self.meta = meta


class FakeRelayRepo:
    def __init__(self, reachable: bool = True, status: str = "active", observed_ip: str = "72.56.109.197") -> None:
        self.reachable = reachable
        self.status = status
        self.observed_ip = observed_ip
        self.calls = 0

    def is_port_reachable(self, timeout: int = 2) -> bool:
        self.calls += 1
        return self.reachable

    def get_remote_service_status(self) -> str:
        self.calls += 1
        return self.status

    def probe_observed_public_ip(self) -> str:
        self.calls += 1
        return self.observed_ip


def build_service(tmp_path: Path) -> tuple[XrayFrontendService, FakeFrontendRepo, FakeMetaRepo, FakeRelayRepo]:
    access_log_path = tmp_path / "access.log"
    config = {
        "inbounds": [
            {
                "tag": "frontend-in",
                "port": 9444,
                "settings": {"clients": [{"id": "client-1", "email": "alpha", "enable": True}]},
                "streamSettings": {
                    "realitySettings": {
                        "privateKey": "priv",
                        "serverNames": ["mitigator.ru"],
                        "target": "mitigator.ru:443",
                        "shortIds": ["aaaaaaaaaaaaaaaa", "bbbbbbbbbbbbbbbb"],
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
    meta = {"clients": {"client-1": {"name": "alpha", "short_id": "aaaaaaaaaaaaaaaa"}}}
    frontend_repo = FakeFrontendRepo(config=config, access_log_path=access_log_path)
    meta_repo = FakeMetaRepo(meta=meta)
    relay_repo = FakeRelayRepo()
    service = XrayFrontendService(
        frontend_repo=frontend_repo,
        meta_repo=meta_repo,
        relay_repo=relay_repo,
        online_window_minutes=5,
        expected_egress_ip="72.56.109.197",
        topology_cache_ttl_seconds=10,
        transport_mode="direct",
        relay_public_host="72.56.109.197",
        relay_private_host="10.10.10.2",
        ipsec_local_tunnel_ip="10.10.10.1",
        ipsec_remote_tunnel_ip="10.10.10.2",
    )
    return service, frontend_repo, meta_repo, relay_repo


def test_list_clients_marks_single_enabled_client_online_when_recent_activity_exists(tmp_path: Path) -> None:
    service, _, meta_repo, _ = build_service(tmp_path)
    seen_at = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S.%f")
    (tmp_path / "access.log").write_text(
        f"{seen_at} from 1.2.3.4:12345 accepted tcp:example.com:443 [frontend-in -> to-relay] email: alpha\n"
    )

    clients = service.list_clients()

    assert len(clients) == 1
    assert clients[0].status == "online"
    assert clients[0].source_ip == "1.2.3.4"
    assert meta_repo.meta["clients"]["client-1"]["source_ip"] == "1.2.3.4"


def test_list_clients_marks_activity_unattributed_when_multiple_enabled_clients_exist(tmp_path: Path) -> None:
    service, frontend_repo, _, _ = build_service(tmp_path)
    frontend_repo.config["inbounds"][0]["settings"]["clients"].append({"id": "client-2", "enable": True})
    seen_at = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S.%f")
    (tmp_path / "access.log").write_text(
        f"{seen_at} from 1.2.3.4:12345 accepted tcp:example.com:443 [frontend-in -> to-relay]\n"
    )

    clients = service.list_clients()

    assert [client.status for client in clients] == ["activity-unattributed", "activity-unattributed"]


def test_create_client_appends_client_and_returns_uri(tmp_path: Path) -> None:
    service, frontend_repo, meta_repo, _ = build_service(tmp_path)

    result = service.create_client(CreateFrontendClientCommand(name="new-client", host="panel.example.com"))

    assert result.client.name == "new-client"
    assert result.client.id in result.uri
    assert "panel.example.com:9444" in result.uri
    assert len(frontend_repo.config["inbounds"][0]["settings"]["clients"]) == 2
    assert result.client.id in meta_repo.meta["clients"]
    assert meta_repo.meta["clients"][result.client.id]["short_id"] == result.client.short_id
    short_ids = frontend_repo.config["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"]
    assert result.client.short_id in short_ids
    assert frontend_repo.restart_calls == 1


def test_create_client_generates_unique_short_id(tmp_path: Path) -> None:
    service, frontend_repo, meta_repo, _ = build_service(tmp_path)

    first = service.create_client(CreateFrontendClientCommand(name="first", host="panel.example.com"))
    second = service.create_client(CreateFrontendClientCommand(name="second", host="panel.example.com"))

    assert first.client.short_id != second.client.short_id
    assert len(set(frontend_repo.config["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"])) == len(
        frontend_repo.config["inbounds"][0]["streamSettings"]["realitySettings"]["shortIds"]
    )
    assert meta_repo.meta["clients"][first.client.id]["short_id"] == first.client.short_id
    assert meta_repo.meta["clients"][second.client.id]["short_id"] == second.client.short_id


def test_create_client_rejects_duplicate_email_name(tmp_path: Path) -> None:
    service, frontend_repo, meta_repo, _ = build_service(tmp_path)
    frontend_repo.config["inbounds"][0]["settings"]["clients"][0]["email"] = "t2"
    meta_repo.meta["clients"]["client-1"]["name"] = "t2"

    try:
        service.create_client(CreateFrontendClientCommand(name="t2", host="panel.example.com"))
        assert False, "expected duplicate client name to be rejected"
    except Exception as exc:
        assert str(exc) == "Client 't2' already exists"


def test_create_client_rejects_duplicate_email_name_case_insensitively(tmp_path: Path) -> None:
    service, frontend_repo, meta_repo, _ = build_service(tmp_path)
    frontend_repo.config["inbounds"][0]["settings"]["clients"][0]["email"] = "Existing"
    meta_repo.meta["clients"]["client-1"]["name"] = "Existing"

    try:
        service.create_client(CreateFrontendClientCommand(name=" existing ", host="panel.example.com"))
        assert False, "expected duplicate client name to be rejected"
    except Exception as exc:
        assert str(exc) == "Client 'existing' already exists"


def test_delete_client_removes_client_from_config_and_meta(tmp_path: Path) -> None:
    service, frontend_repo, meta_repo, _ = build_service(tmp_path)

    deleted = service.delete_client("client-1")

    assert deleted is True
    assert frontend_repo.config["inbounds"][0]["settings"]["clients"] == []
    assert meta_repo.meta["clients"] == {}
    assert frontend_repo.restart_calls == 1


def test_set_client_enabled_sets_false(tmp_path: Path) -> None:
    service, frontend_repo, _, _ = build_service(tmp_path)

    result = service.set_client_enabled("client-1", False)

    assert result is not None
    assert result.enabled is False
    # Client is removed from xray config (xray VLESS ignores enable flag)
    assert frontend_repo.config["inbounds"][0]["settings"]["clients"] == []
    assert frontend_repo.restart_calls == 1


def test_set_client_enabled_sets_true(tmp_path: Path) -> None:
    service, frontend_repo, meta_repo, _ = build_service(tmp_path)
    # First disable so client is removed from config
    service.set_client_enabled("client-1", False)
    assert frontend_repo.config["inbounds"][0]["settings"]["clients"] == []

    result = service.set_client_enabled("client-1", True)

    assert result is not None
    assert result.enabled is True
    clients_in_config = frontend_repo.config["inbounds"][0]["settings"]["clients"]
    assert len(clients_in_config) == 1
    assert clients_in_config[0]["id"] == "client-1"


def test_validate_frontend_config_runs_preflight_without_restart(tmp_path: Path) -> None:
    service, frontend_repo, _, _ = build_service(tmp_path)

    result = service.validate_frontend_config(
        UpdateFrontendConfigCommand(
            port=9555,
            server_name="example.org",
            fingerprint="chrome",
            target="example.org:443",
            spider_x="/health",
            short_ids=["cccccccccccccccc", "dddddddddddddddd"],
            relay_host="10.0.0.2",
            relay_port=9556,
        )
    )

    assert result.preflight_ok is True
    assert result.status == "validated"
    assert frontend_repo.restart_calls == 0


def test_update_frontend_config_updates_runtime_config(tmp_path: Path) -> None:
    service, frontend_repo, _, _ = build_service(tmp_path)

    result = service.update_frontend_config(
        UpdateFrontendConfigCommand(
            port=9555,
            server_name="example.org",
            fingerprint="chrome",
            target="example.org:443",
            spider_x="/health",
            short_ids=["cccccccccccccccc", "dddddddddddddddd"],
            relay_host="10.0.0.2",
            relay_port=9556,
        )
    )

    assert result.port == 9555
    assert result.server_name == "example.org"
    assert result.relay_host == "10.0.0.2"
    assert frontend_repo.restart_calls == 1


def test_update_relay_config_updates_frontend_outbound(tmp_path: Path) -> None:
    service, frontend_repo, _, _ = build_service(tmp_path)

    result = service.update_relay_config(
        UpdateRelayConfigCommand(
            public_host="203.0.113.10",
            listen_port=9777,
            relay_uuid="relay-new",
        )
    )

    assert result.host == "203.0.113.10"
    assert result.port == 9777
    assert result.uuid == "relay-new"
    assert frontend_repo.restart_calls == 1


def test_get_topology_health_uses_cached_value_within_ttl(tmp_path: Path) -> None:
    service, _, _, relay_repo = build_service(tmp_path)

    first = service.get_topology_health()
    second = service.get_topology_health()

    assert first.relay_service == "active"
    assert second.relay_service == "active"
    assert first.egress_probe_ok is True
    assert first.observed_egress_ip == "72.56.109.197"
    assert first.frontend_ready is True
    assert first.transport_mode == "direct"
    assert first.transport_label == "Direct public relay"
    assert first.active_relay_host == "72.56.109.197"
    assert first.ipsec_active is False
    assert second.relay_service == "active"
    assert relay_repo.calls == 3


def test_get_topology_health_marks_ipsec_active_after_private_cutover(tmp_path: Path) -> None:
    service, frontend_repo, _, relay_repo = build_service(tmp_path)
    service._topology._transport_mode = TransportMode.from_string("ipsec")
    frontend_repo.config["outbounds"][0]["settings"]["vnext"][0]["address"] = "10.10.10.2"
    relay_repo.observed_ip = "72.56.109.197"

    result = service.get_topology_health()

    assert result.transport_mode == "ipsec"
    assert result.transport_label == "IPSec private relay"
    assert result.ipsec_expected is True
    assert result.ipsec_active is True
    assert result.active_relay_host == "10.10.10.2"
    assert result.relay_private_host == "10.10.10.2"
    assert result.ipsec_local_tunnel_ip == "10.10.10.1"
    assert result.ipsec_remote_tunnel_ip == "10.10.10.2"
    assert relay_repo.calls == 3


def test_get_topology_health_marks_ipsec_degraded_when_private_relay_is_unreachable(tmp_path: Path) -> None:
    service, frontend_repo, _, relay_repo = build_service(tmp_path)
    service._topology._transport_mode = TransportMode.from_string("ipsec")
    frontend_repo.config["outbounds"][0]["settings"]["vnext"][0]["address"] = "10.10.10.2"
    relay_repo.reachable = False

    result = service.get_topology_health()

    assert result.transport_mode == "ipsec"
    assert result.ipsec_expected is True
    assert result.ipsec_active is False
    assert result.transport_label == "IPSec degraded: private relay unreachable"
    assert result.relay_reachable is False


def test_list_clients_marks_client_offline_when_last_seen_is_old(tmp_path: Path) -> None:
    service, _, meta_repo, _ = build_service(tmp_path)
    old_seen_at = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    meta_repo.meta["clients"]["client-1"]["last_seen"] = old_seen_at

    clients = service.list_clients()

    assert clients[0].status == "offline"
