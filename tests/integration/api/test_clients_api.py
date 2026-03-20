from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import FrontendClient, FrontendClientUriResult
from app.main import app
from tests.conftest import create_test_client


class FakeClientsService:
    def __init__(self) -> None:
        self.clients = [
            FrontendClient(
                id="client-1",
                name="alpha",
                short_id="sid-a",
                status="online",
                enabled=True,
            )
        ]

    def list_clients(self):
        return self.clients

    def create_client(self, command):
        client = FrontendClient(id="client-2", name=command.name, short_id="sid-b", enabled=True)
        self.clients.append(client)
        return FrontendClientUriResult(client=client, uri="vless://client-2@test:9444")

    def delete_client(self, client_id: str) -> bool:
        before = len(self.clients)
        self.clients = [item for item in self.clients if item.id != client_id]
        return len(self.clients) != before

    def set_client_enabled(self, client_id: str, enabled: bool) -> bool:
        target = next((item for item in self.clients if item.id == client_id), None)
        if target is None:
            return False
        target.enabled = enabled
        return True


def test_create_client_returns_201_and_uri() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeClientsService()
    client = create_test_client()

    response = client.post(
        "/api/xray-frontend/clients",
        auth=("admin", "change-me"),
        json={"name": "bravo", "host": "panel.example.com"},
    )

    assert response.status_code == 201
    assert response.json()["client"]["name"] == "bravo"
    assert response.json()["uri"] == "vless://client-2@test:9444"
    app.dependency_overrides.clear()


def test_delete_client_returns_204() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeClientsService()
    client = create_test_client()

    response = client.delete(
        "/api/xray-frontend/clients/client-1",
        auth=("admin", "change-me"),
    )

    assert response.status_code == 204
    app.dependency_overrides.clear()


def test_enable_client_returns_updated_client() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeClientsService()
    client = create_test_client()

    response = client.post(
        "/api/xray-frontend/clients/client-1/enable",
        auth=("admin", "change-me"),
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is True
    app.dependency_overrides.clear()


def test_disable_client_returns_updated_client() -> None:
    app.dependency_overrides[get_xray_frontend_service] = lambda: FakeClientsService()
    client = create_test_client()

    response = client.post(
        "/api/xray-frontend/clients/client-1/disable",
        auth=("admin", "change-me"),
    )

    assert response.status_code == 200
    assert response.json()["enabled"] is False
    app.dependency_overrides.clear()
