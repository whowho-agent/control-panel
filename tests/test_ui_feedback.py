from fastapi.testclient import TestClient

from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import (
    FrontendApplyResult,
    FrontendClient,
    FrontendConfigResult,
    RelayConfigResult,
    TopologyHealthResult,
)
from app.main import app


class FakeUiService:
    def get_topology_health(self):
        return TopologyHealthResult(
            frontend_service="configured",
            relay_service="active",
            relay_reachable=True,
            expected_egress_ip="72.56.109.197",
            client_count=1,
            online_count=1,
            egress_probe_ok=True,
            observed_egress_ip="72.56.109.197",
            frontend_ready=True,
            frontend_readiness_status="ready",
        )

    def get_frontend_config(self):
        return FrontendConfigResult(
            port=9444,
            server_name="mitigator.ru",
            public_key="pub",
            private_key="priv",
            fingerprint="firefox",
            short_ids=["aaaaaaaaaaaaaaaa"],
            spider_x="/",
            target="mitigator.ru:443",
            relay_host="72.56.109.197",
            relay_port=9443,
            relay_uuid="00000000-0000-0000-0000-000000000001",
        )

    def get_relay_config(self):
        return RelayConfigResult(
            host="72.56.109.197",
            port=9443,
            uuid="00000000-0000-0000-0000-000000000001",
        )

    def list_clients(self):
        return [FrontendClient(id="client-1", name="test-client", short_id="aaaaaaaaaaaaaaaa", status="online")]

    def build_client_uri(self, host, client, frontend_config):
        return f"vless://{client.id}@{host}:{frontend_config.port}"

    def create_client(self, command):
        if command.name == "dupe":
            from app.domain.xray_frontend import ControlPlaneError
            raise ControlPlaneError("client_name_exists", "Client 'dupe' already exists", status_code=409)
        return None

    def delete_client(self, client_id: str):
        return client_id == "client-1"

    def set_client_enabled(self, client_id: str, enabled: bool):
        return client_id == "client-1"

    def update_frontend_config(self, command):
        return self.get_frontend_config()

    def update_relay_config(self, command):
        return self.get_relay_config()

    def validate_frontend_config(self, command):
        return FrontendApplyResult(True, False, False, "validated", "Config validation passed")

    def validate_relay_config(self, command):
        return FrontendApplyResult(True, False, False, "validated", "Config validation passed")

    def get_sniffing_config(self):
        from app.domain.xray_frontend import SniffingConfigResult
        return SniffingConfigResult(enabled=False, dest_override=[], route_only=False)

    def get_recent_activity(self, minutes, limit=100):
        return []


def test_clients_page_renders_flash_messages() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.get(
        "/clients?success=client_created&error=client_not_found", auth=("admin", "change-me")
    )

    assert response.status_code == 200
    assert "Client created and frontend is ready." in response.text
    assert "Client not found." in response.text
    app.dependency_overrides.clear()


def test_create_client_redirects_with_error_message_on_duplicate() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.post(
        "/clients",
        auth=("admin", "change-me"),
        data={"name": "dupe"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/clients?error=Client+%27dupe%27+already+exists"
    app.dependency_overrides.clear()


def test_update_relay_config_redirects_with_error_on_invalid_uuid() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.post(
        "/config/relay",
        auth=("admin", "change-me"),
        data={
            "relay_public_host": "72.56.109.197",
            "relay_listen_port": 9443,
            "relay_uuid": "not-a-uuid",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"].startswith("/config?error=")
    app.dependency_overrides.clear()


def test_validate_frontend_config_redirects_with_success_message() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.post(
        "/config/frontend/validate",
        auth=("admin", "change-me"),
        data={
            "frontend_port": 9444,
            "frontend_sni": "mitigator.ru",
            "frontend_fp": "firefox",
            "frontend_target": "mitigator.ru:443",
            "frontend_spider": "/",
            "frontend_shortids": "aaaaaaaaaaaaaaaa",
            "relay_host": "72.56.109.197",
            "relay_port": 9443,
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/config?success=frontend_config_valid"
    app.dependency_overrides.clear()
