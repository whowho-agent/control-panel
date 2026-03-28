from fastapi.testclient import TestClient

from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import (
    FrontendApplyResult,
    FrontendClient,
    FrontendConfigResult,
    RelayConfigResult,
    SniffingConfigResult,
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
            short_ids=["sid"],
            spider_x="/",
            target="mitigator.ru:443",
            relay_host="72.56.109.197",
            relay_port=9443,
            relay_uuid="uuid",
        )

    def get_relay_config(self):
        return RelayConfigResult(host="72.56.109.197", port=9443, uuid="uuid")

    def list_clients(self):
        return [
            FrontendClient(
                id="client-1",
                name="test-client",
                short_id="sid",
                status="activity-unattributed",
                enabled=True,
            )
        ]

    def build_client_uri(self, host, client, frontend_config):
        return f"vless://{client.id}@{host}:{frontend_config.port}"

    def create_client(self, command):
        return None

    def delete_client(self, client_id: str):
        return True

    def set_client_enabled(self, client_id: str, enabled: bool):
        return True

    def update_frontend_config(self, command):
        return self.get_frontend_config()

    def update_relay_config(self, command):
        return self.get_relay_config()

    def validate_frontend_config(self, command):
        return FrontendApplyResult(True, False, False, "validated", "Config validation passed")

    def validate_relay_config(self, command):
        return FrontendApplyResult(True, False, False, "validated", "Config validation passed")

    def get_sniffing_config(self):
        return SniffingConfigResult(enabled=False, dest_override=[], route_only=False)

    def update_sniffing_config(self, command):
        return self.get_sniffing_config()

    def get_recent_activity(self, minutes, limit=100):
        return []


def test_clients_page_renders_with_basic_auth() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.get("/clients", auth=("admin", "change-me"))

    assert response.status_code == 200
    assert "test-client" in response.text
    assert "activity-unattributed" in response.text
    assert "QR" in response.text
    assert "safe apply workflow" in response.text
    app.dependency_overrides.clear()


def test_config_page_renders_with_basic_auth() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.get("/config", auth=("admin", "change-me"))

    assert response.status_code == 200
    assert "Config Editor" in response.text
    assert "Relay config" in response.text
    assert "Validate only" in response.text
    app.dependency_overrides.clear()


def test_client_qr_returns_png() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.get("/clients/client-1/qr", auth=("admin", "change-me"))

    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    app.dependency_overrides.clear()


def test_update_frontend_config_form_redirects() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.post(
        "/config/frontend",
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
    assert response.headers["location"] == "/config?success=frontend_config_saved"
    app.dependency_overrides.clear()


def test_update_relay_config_form_redirects() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeUiService()
    client = TestClient(app)

    response = client.post(
        "/config/relay",
        auth=("admin", "change-me"),
        data={
            "relay_public_host": "72.56.109.197",
            "relay_listen_port": 9443,
            "relay_uuid": "00000000-0000-0000-0000-000000000001",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/config?success=relay_config_saved"
    app.dependency_overrides.clear()


def test_dashboard_and_config_show_ipsec_transport_context() -> None:
    class FakeIpsecUiService(FakeUiService):
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
                transport_mode="ipsec",
                transport_label="IPSec private relay",
                relay_public_host="72.56.109.197",
                relay_private_host="10.10.10.2",
                active_relay_host="10.10.10.2",
                active_relay_port=9443,
                ipsec_expected=True,
                ipsec_active=True,
                ipsec_local_tunnel_ip="10.10.10.1",
                ipsec_remote_tunnel_ip="10.10.10.2",
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
                relay_host="10.10.10.2",
                relay_port=9443,
                relay_uuid="uuid",
            )

        def get_relay_config(self):
            return RelayConfigResult(host="10.10.10.2", port=9443, uuid="uuid")

    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeIpsecUiService()
    client = TestClient(app)

    dashboard = client.get("/", auth=("admin", "change-me"))
    config = client.get("/config", auth=("admin", "change-me"))

    assert dashboard.status_code == 200
    assert "IPSec private relay" in dashboard.text
    assert "10.10.10.1" in dashboard.text
    assert config.status_code == 200
    assert "Expected private relay" in config.text
    assert "10.10.10.2" in config.text
    app.dependency_overrides.clear()


def test_dashboard_shows_ipsec_degraded_label_when_private_path_is_down() -> None:
    class FakeIpsecDegradedUiService(FakeUiService):
        def get_topology_health(self):
            return TopologyHealthResult(
                frontend_service="configured",
                relay_service="active",
                relay_reachable=False,
                expected_egress_ip="72.56.109.197",
                client_count=1,
                online_count=1,
                egress_probe_ok=True,
                observed_egress_ip="72.56.109.197",
                frontend_ready=True,
                frontend_readiness_status="ready",
                transport_mode="ipsec",
                transport_label="IPSec degraded: private relay unreachable",
                relay_public_host="72.56.109.197",
                relay_private_host="10.10.10.2",
                active_relay_host="10.10.10.2",
                active_relay_port=9443,
                ipsec_expected=True,
                ipsec_active=False,
                ipsec_local_tunnel_ip="10.10.10.1",
                ipsec_remote_tunnel_ip="10.10.10.2",
            )

    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeIpsecDegradedUiService()
    client = TestClient(app)

    dashboard = client.get("/", auth=("admin", "change-me"))

    assert dashboard.status_code == 200
    assert "IPSec degraded: private relay unreachable" in dashboard.text
    assert "private relay unreachable or cutover incomplete" in dashboard.text
    app.dependency_overrides.clear()
