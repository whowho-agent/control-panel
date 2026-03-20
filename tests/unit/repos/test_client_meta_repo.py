import json
from pathlib import Path

from app.repos.client_meta_repo import ClientMetaRepo


def test_read_returns_empty_clients_when_file_missing(tmp_path: Path) -> None:
    repo = ClientMetaRepo(str(tmp_path / "clients-meta.json"))

    assert repo.read() == {"clients": {}}


def test_read_tolerates_literal_backslash_n_suffix(tmp_path: Path) -> None:
    meta_path = tmp_path / "clients-meta.json"
    meta_path.write_text('{"clients": {"client-1": {"name": "alpha"}}}\\n')
    repo = ClientMetaRepo(str(meta_path))

    assert repo.read() == {"clients": {"client-1": {"name": "alpha"}}}


def test_read_returns_empty_clients_for_blank_file(tmp_path: Path) -> None:
    meta_path = tmp_path / "clients-meta.json"
    meta_path.write_text("")
    repo = ClientMetaRepo(str(meta_path))

    assert repo.read() == {"clients": {}}


def test_write_normalizes_json_newline(tmp_path: Path) -> None:
    meta_path = tmp_path / "clients-meta.json"
    repo = ClientMetaRepo(str(meta_path))

    repo.write({"clients": {"client-1": {"name": "alpha"}}})

    assert json.loads(meta_path.read_text()) == {"clients": {"client-1": {"name": "alpha"}}}
    assert meta_path.read_text().endswith("\n")
