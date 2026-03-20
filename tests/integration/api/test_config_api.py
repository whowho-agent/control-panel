from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import FrontendConfigResult, RelayConfigResult, TopologyHealthResult
from app.main import app
from tests.conftest import create_test_client


class FakeConfigService:
    def get_frontend_config(self):
        return FrontendConfigResult(
            port=9444,
            server_name="mitigator.ru",
            public_key="pub",
            private_key="priv",
            fingerprint="firefox",
            short_ids=["sid-a", "sid-b"],
            spider_x="/",
            target="mitigator.ru:443",
            relay_host="72.56.109.197",
            relay_port=9443,
            relay_uuid="relay-uuid",
        )

    def update_frontend_config(self, command):
        return FrontendConfigResult(
            port=command.port,
            server_name=command.server_name,
            public_key="pub",
            private_key="priv",
            fingerprint=command.fingerprint,
            short_ids=command.short_ids,
            spider_x=command.spider_x,
            target=command.target,
            relay_host=command.relay_host,
            relay_port=command.relay_port,
            relay_uuid="relay-uuid",
        )

    def get_relay_config(self):
        return RelayConfigResult(host="72.56.109.197", port=9443, uuid="relay-uuid")

    def update_relay_config(self, command):
        return RelayConfigResult(
            host=command.public_host,
            port=command.listen_port,
            uuid=command.relay_uuid,
        )

    def get_topology_health(self):
        return TopologyHealthResult(
            frontend_service="configured",
            relay_service="active",
            relay_reachable=True,
            expected_egress_ip="72.56.109.197",
            client_count=0,
            online_count=0,
            egress_probe_ok=True,
            observed_egress_ip="72.56.109.197",
        )


def test_get_frontend_config_returns_runtime_values() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeConfigService()
    client = create_test_client()

    response = client.get(
        "/api/xray-frontend/config/frontend",
        auth=("admin", "change-me"),
    )

    assert response.status_code == 200
    assert response.json()["port"] == 9444
    assert response.json()["relay_host"] == "72.56.109.197"
    app.dependency_overrides.clear()


def test_update_frontend_config_returns_updated_payload() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeConfigService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/frontend",
        auth=("admin", "change-me"),
        json={
            "port": 9555,
            "server_name": "example.org",
            "fingerprint": "chrome",
            "target": "example.org:443",
            "spider_x": "/health",
            "short_ids": ["sid-1"],
            "relay_host": "10.0.0.2",
            "relay_port": 9556,
        },
    )

    assert response.status_code == 200
    assert response.json()["port"] == 9555
    assert response.json()["server_name"] == "example.org"
    app.dependency_overrides.clear()


def test_get_relay_config_returns_runtime_values() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeConfigService()
    client = create_test_client()

    response = client.get(
        "/api/xray-frontend/config/relay",
        auth=("admin", "change-me"),
    )

    assert response.status_code == 200
    assert response.json()["host"] == "72.56.109.197"
    assert response.json()["uuid"] == "relay-uuid"
    app.dependency_overrides.clear()


def test_update_relay_config_returns_updated_payload() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeConfigService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/relay",
        auth=("admin", "change-me"),
        json={
            "public_host": "203.0.113.5",
            "listen_port": 9777,
            "relay_uuid": "relay-new",
        },
    )

    assert response.status_code == 200
    assert response.json()["host"] == "203.0.113.5"
    assert response.json()["port"] == 9777
    assert response.json()["uuid"] == "relay-new"
    app.dependency_overrides.clear()
