from app.repos.relay_node_repo import RelayNodeRepo


class DummySocket:
    def __init__(self):
        self.opened = False

    def __enter__(self):
        self.opened = True
        return self

    def __exit__(self, exc_type, exc, tb):
        return False


def test_is_port_reachable_returns_true_when_connection_succeeds(monkeypatch) -> None:
    repo = RelayNodeRepo(
        host="72.56.109.197",
        port=9443,
        service_name="xray-relay",
        ssh_key_path="/tmp/key",
        ssh_user="root",
    )

    monkeypatch.setattr("socket.create_connection", lambda *args, **kwargs: DummySocket())

    assert repo.is_port_reachable() is True


def test_get_remote_service_status_returns_unknown_on_ssh_error(monkeypatch) -> None:
    repo = RelayNodeRepo(
        host="72.56.109.197",
        port=9443,
        service_name="xray-relay",
        ssh_key_path="/tmp/key",
        ssh_user="root",
    )

    class Result:
        returncode = 1
        stdout = ""
        stderr = "ssh failed"

    monkeypatch.setattr("subprocess.run", lambda *args, **kwargs: Result())

    assert repo.get_remote_service_status() == "unknown"
