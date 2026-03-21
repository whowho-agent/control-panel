from app.api.deps import get_xray_frontend_service
from app.main import app
from tests.conftest import create_test_client
from tests.integration.api.test_config_api import FakeConfigService


def test_update_frontend_config_rejects_invalid_short_id() -> None:
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
            "short_ids": ["INVALID-UPPERCASE"],
            "relay_host": "10.0.0.2",
            "relay_port": 9556,
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_update_relay_config_rejects_invalid_uuid() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeConfigService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/relay",
        auth=("admin", "change-me"),
        json={
            "public_host": "203.0.113.5",
            "listen_port": 9777,
            "relay_uuid": "not-a-uuid",
        },
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_create_client_rejects_blank_name() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeConfigService()
    client = create_test_client()

    response = client.post(
        "/api/xray-frontend/clients",
        auth=("admin", "change-me"),
        json={"name": "   ", "host": "panel.example.com"},
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()
