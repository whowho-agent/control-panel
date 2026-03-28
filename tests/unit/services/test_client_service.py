from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

from app.domain.xray_config import XrayConfigAccessor
from app.domain.xray_frontend import CreateFrontendClientCommand, FrontendApplyResult, FrontendConfigResult
from app.services.client_service import ClientService


class FakeFrontendRepo:
    def __init__(self, config: dict, access_log_path: Path) -> None:
        self.config = config
        self.access_log_path = access_log_path
        self.restart_calls = 0
        self.apply_result = FrontendApplyResult(True, True, True, "ready", "ok")

    def read_config(self) -> XrayConfigAccessor:
        return XrayConfigAccessor(self.config)

    def apply_config(self, config: XrayConfigAccessor) -> FrontendApplyResult:
        self.config = config.to_dict()
        if self.apply_result.restarted:
            self.restart_calls += 1
        return self.apply_result

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

    def parse_activity(self) -> dict:
        from app.repos.xray_frontend_repo import XrayFrontendRepo
        repo = XrayFrontendRepo.__new__(XrayFrontendRepo)
        repo.access_log_path = self.access_log_path
        return repo.parse_activity()


class FakeMetaRepo:
    def __init__(self, meta: dict) -> None:
        self.meta = meta

    def read(self) -> dict:
        return self.meta

    def write(self, meta: dict) -> None:
        self.meta = meta


def _base_config() -> dict:
    return {
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
                        "shortIds": ["aaaaaaaaaaaaaaaa"],
                        "settings": {"fingerprint": "firefox", "spiderX": "/"},
                    }
                },
            }
        ],
        "outbounds": [
            {
                "tag": "to-relay",
                "settings": {"vnext": [{"address": "1.2.3.4", "port": 9443, "users": [{"id": "uuid"}]}]},
            }
        ],
    }


def build_service(tmp_path: Path) -> tuple[ClientService, FakeFrontendRepo, FakeMetaRepo]:
    access_log = tmp_path / "access.log"
    meta = {"clients": {"client-1": {"name": "alpha", "short_id": "aaaaaaaaaaaaaaaa"}}}
    repo = FakeFrontendRepo(config=_base_config(), access_log_path=access_log)
    meta_repo = FakeMetaRepo(meta=meta)
    svc = ClientService(frontend_repo=repo, meta_repo=meta_repo, online_window_minutes=5)
    return svc, repo, meta_repo


def test_list_returns_clients(tmp_path: Path) -> None:
    svc, _, _ = build_service(tmp_path)
    clients = svc.list()
    assert len(clients) == 1
    assert clients[0].id == "client-1"
    assert clients[0].name == "alpha"


def test_list_marks_online_when_recent_activity(tmp_path: Path) -> None:
    svc, _, meta_repo = build_service(tmp_path)
    ts = datetime.now(timezone.utc).strftime("%Y/%m/%d %H:%M:%S.%f")
    (tmp_path / "access.log").write_text(
        f"{ts} from 1.2.3.4:12345 accepted tcp:example.com:443 [frontend-in -> to-relay] email: alpha\n"
    )
    clients = svc.list()
    assert clients[0].status == "online"
    assert meta_repo.meta["clients"]["client-1"]["source_ip"] == "1.2.3.4"


def test_list_marks_offline_when_stale_last_seen(tmp_path: Path) -> None:
    svc, _, meta_repo = build_service(tmp_path)
    old = (datetime.now(timezone.utc) - timedelta(minutes=30)).isoformat().replace("+00:00", "Z")
    meta_repo.meta["clients"]["client-1"]["last_seen"] = old
    clients = svc.list()
    assert clients[0].status == "offline"


def test_create_appends_client_and_returns_uri(tmp_path: Path) -> None:
    svc, repo, meta_repo = build_service(tmp_path)
    result = svc.create(CreateFrontendClientCommand(name="bob", host="panel.example.com"))
    assert result.client.name == "bob"
    assert result.client.id in result.uri
    assert "panel.example.com:9444" in result.uri
    assert len(repo.config["inbounds"][0]["settings"]["clients"]) == 2
    assert result.client.id in meta_repo.meta["clients"]


def test_create_rejects_duplicate_name(tmp_path: Path) -> None:
    svc, repo, _ = build_service(tmp_path)
    repo.config["inbounds"][0]["settings"]["clients"][0]["email"] = "alice"
    with pytest.raises(Exception, match="already exists"):
        svc.create(CreateFrontendClientCommand(name="alice", host="h"))


def test_delete_removes_client(tmp_path: Path) -> None:
    svc, repo, meta_repo = build_service(tmp_path)
    deleted = svc.delete("client-1")
    assert deleted is True
    assert repo.config["inbounds"][0]["settings"]["clients"] == []
    assert meta_repo.meta["clients"] == {}


def test_delete_returns_false_for_unknown_id(tmp_path: Path) -> None:
    svc, _, _ = build_service(tmp_path)
    assert svc.delete("no-such-id") is False


def test_set_enabled_false(tmp_path: Path) -> None:
    svc, repo, _ = build_service(tmp_path)
    assert svc.set_enabled("client-1", False) is True
    assert repo.config["inbounds"][0]["settings"]["clients"][0]["enable"] is False


def test_set_enabled_returns_false_for_unknown_id(tmp_path: Path) -> None:
    svc, _, _ = build_service(tmp_path)
    assert svc.set_enabled("no-such-id", True) is False
