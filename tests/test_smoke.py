from tests.conftest import create_test_client


def test_health_returns_ok() -> None:
    client = create_test_client()

    response = client.get('/health')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


def test_dashboard_requires_basic_auth() -> None:
    client = create_test_client()

    response = client.get('/')

    assert response.status_code == 401


def test_clients_api_requires_basic_auth() -> None:
    client = create_test_client()

    response = client.get('/api/xray-frontend/clients')

    assert response.status_code == 401
