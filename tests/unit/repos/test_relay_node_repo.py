import httpx

from app.repos.relay_node_repo import RelayNodeRepo


class DummySocket:
    def __init__(self):
        self.opened = False

    def __enter__(self):
        self.opened = True
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def make_repo(agent_url: str = "http://10.0.0.1:9100") -> RelayNodeRepo:
    return RelayNodeRepo(host="147.45.152.57", port=9443, agent_url=agent_url)


def test_is_port_reachable_returns_true_when_connection_succeeds(monkeypatch) -> None:
    repo = make_repo()
    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: DummySocket())
    assert repo.is_port_reachable() is True


def test_is_port_reachable_returns_false_on_os_error(monkeypatch) -> None:
    repo = make_repo()

    def fail(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr("socket.create_connection", fail)
    assert repo.is_port_reachable() is False


def _mock_httpx_get(monkeypatch, payload: dict | None = None, exc: Exception | None = None) -> None:
    def fake_get(url, **kwargs):
        if exc is not None:
            raise exc
        return httpx.Response(200, json=payload)

    monkeypatch.setattr("httpx.get", fake_get)


def test_get_remote_service_status_returns_value_from_agent(monkeypatch) -> None:
    _mock_httpx_get(monkeypatch, payload={"service": "active", "egress_ip": "1.2.3.4", "updated_at": 0.0})
    repo = make_repo()
    assert repo.get_remote_service_status() == "active"


def test_get_remote_service_status_returns_unknown_on_error(monkeypatch) -> None:
    _mock_httpx_get(monkeypatch, exc=httpx.ConnectError("refused"))
    repo = make_repo()
    assert repo.get_remote_service_status() == "unknown"


def test_probe_observed_public_ip_returns_ip_from_agent(monkeypatch) -> None:
    _mock_httpx_get(monkeypatch, payload={"service": "active", "egress_ip": "1.2.3.4", "updated_at": 0.0})
    repo = make_repo()
    assert repo.probe_observed_public_ip() == "1.2.3.4"


def test_probe_observed_public_ip_returns_empty_on_error(monkeypatch) -> None:
    _mock_httpx_get(monkeypatch, exc=httpx.ConnectError("refused"))
    repo = make_repo()
    assert repo.probe_observed_public_ip() == ""
