from fastapi.testclient import TestClient

from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import FrontendClient, FrontendConfigResult, TopologyHealthResult
from app.main import app


class FakeService:
    def get_topology_health(self):
        return TopologyHealthResult(
            frontend_service="configured",
            relay_service="active",
            relay_reachable=True,
            expected_egress_ip="72.56.109.197",
            client_count=1,
            online_count=1,
        )

    def get_frontend_config(self):
        return FrontendConfigResult(
            port=9444,
            server_name="mitigator.ru",
            public_key="pub",
            private_key="priv",
            fingerprint="firefox",
            short_ids=["sid"],
            spider_x="/",
            target="mitigator.ru:443",
            relay_host="72.56.109.197",
            relay_port=9443,
            relay_uuid="uuid",
        )

    def list_clients(self):
        return [
            FrontendClient(
                id="client-1",
                name="test-client",
                short_id="sid",
                status="online",
                enabled=True,
            )
        ]

    def build_client_uri(self, host, client, frontend_config):
        return f"vless://{client.id}@{host}:{frontend_config.port}"


def test_dashboard_renders_with_basic_auth() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeService()
    client = TestClient(app)

    response = client.get("/", auth=("admin", "change-me"))

    assert response.status_code == 200
    assert "Dashboard" in response.text
    assert "72.56.109.197" in response.text
    assert "testserver" in response.text
    app.dependency_overrides.clear()

    app.dependency_overrides.clear()
