from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import SniffingConfigResult
from app.main import app
from tests.conftest import create_test_client


class FakeSniffingService:
    def get_sniffing_config(self):
        return SniffingConfigResult(
            enabled=True,
            dest_override=["http", "tls", "quic"],
            route_only=False,
        )

    def update_sniffing_config(self, command):
        return SniffingConfigResult(
            enabled=command.enabled,
            dest_override=command.dest_override,
            route_only=command.route_only,
        )


def test_get_sniffing_config_returns_current_state() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeSniffingService()
    client = create_test_client()

    response = client.get("/api/xray-frontend/config/sniffing", auth=("admin", "change-me"))

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    assert data["dest_override"] == ["http", "tls", "quic"]
    assert data["route_only"] is False
    app.dependency_overrides.clear()


def test_put_sniffing_config_returns_updated_state() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeSniffingService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/sniffing",
        auth=("admin", "change-me"),
        json={"enabled": False, "dest_override": ["fakedns"], "route_only": True},
    )

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is False
    assert data["dest_override"] == ["fakedns"]
    assert data["route_only"] is True
    app.dependency_overrides.clear()


def test_put_sniffing_config_rejects_invalid_dest_override() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeSniffingService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/sniffing",
        auth=("admin", "change-me"),
        json={"enabled": True, "dest_override": ["udp"], "route_only": False},
    )

    assert response.status_code == 422
    app.dependency_overrides.clear()


def test_put_sniffing_config_allows_empty_dest_override() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeSniffingService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/sniffing",
        auth=("admin", "change-me"),
        json={"enabled": True, "dest_override": [], "route_only": False},
    )

    assert response.status_code == 200
    assert response.json()["dest_override"] == []
    app.dependency_overrides.clear()


def test_put_sniffing_config_deduplicates_dest_override() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeSniffingService()
    client = create_test_client()

    response = client.put(
        "/api/xray-frontend/config/sniffing",
        auth=("admin", "change-me"),
        json={"enabled": True, "dest_override": ["http", "http", "tls"], "route_only": False},
    )

    assert response.status_code == 200
    assert response.json()["dest_override"] == ["http", "tls"]
    app.dependency_overrides.clear()
