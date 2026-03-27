import json
from pathlib import Path

from deploy.bootstrap.restore_clients import restore_clients


def _write_config(path: Path, clients: list) -> None:
    config = {
        "inbounds": [
            {
                "tag": "frontend-in",
                "port": 9444,
                "settings": {"clients": clients},
                "streamSettings": {
                    "realitySettings": {
                        "shortIds": ["aabbccdd11223344"],
                        "privateKey": "priv",
                        "serverNames": ["example.com"],
                        "target": "example.com:443",
                    }
                },
            }
        ],
        "outbounds": [],
    }
    path.write_text(json.dumps(config))


def _write_meta(path: Path, clients: dict) -> None:
    path.write_text(json.dumps({"clients": clients}))


def _read_config(path: Path) -> dict:
    return json.loads(path.read_text())


def test_restores_clients_into_empty_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    _write_meta(meta_path, {
        "abc-123": {"name": "msk-nb", "short_id": "aabbccdd11223344"},
        "def-456": {"name": "msk-iphone", "short_id": "eeff00112233aabb"},
    })

    count = restore_clients(config_path, meta_path)

    assert count == 2
    config = _read_config(config_path)
    inbound = next(i for i in config["inbounds"] if i["tag"] == "frontend-in")
    ids = {c["id"] for c in inbound["settings"]["clients"]}
    assert ids == {"abc-123", "def-456"}


def test_restored_client_email_matches_meta_name(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    _write_meta(meta_path, {"abc-123": {"name": "msk-nb", "short_id": "aabbccdd11223344"}})

    restore_clients(config_path, meta_path)

    config = _read_config(config_path)
    inbound = next(i for i in config["inbounds"] if i["tag"] == "frontend-in")
    client = inbound["settings"]["clients"][0]
    assert client["email"] == "msk-nb"


def test_restored_short_id_added_to_reality(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    _write_meta(meta_path, {"abc-123": {"name": "msk-nb", "short_id": "eeff00112233aabb"}})

    restore_clients(config_path, meta_path)

    config = _read_config(config_path)
    inbound = next(i for i in config["inbounds"] if i["tag"] == "frontend-in")
    short_ids = inbound["streamSettings"]["realitySettings"]["shortIds"]
    assert "eeff00112233aabb" in short_ids


def test_does_not_duplicate_already_present_short_id(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    _write_meta(meta_path, {"abc-123": {"name": "msk-nb", "short_id": "aabbccdd11223344"}})

    restore_clients(config_path, meta_path)

    config = _read_config(config_path)
    inbound = next(i for i in config["inbounds"] if i["tag"] == "frontend-in")
    short_ids = inbound["streamSettings"]["realitySettings"]["shortIds"]
    assert short_ids.count("aabbccdd11223344") == 1


def test_skips_clients_already_in_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [{"id": "abc-123", "email": "msk-nb"}])
    _write_meta(meta_path, {"abc-123": {"name": "msk-nb", "short_id": "aabbccdd11223344"}})

    count = restore_clients(config_path, meta_path)

    assert count == 0
    config = _read_config(config_path)
    inbound = next(i for i in config["inbounds"] if i["tag"] == "frontend-in")
    assert len(inbound["settings"]["clients"]) == 1


def test_returns_zero_and_does_not_write_when_meta_missing(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    mtime_before = config_path.stat().st_mtime

    count = restore_clients(config_path, meta_path)

    assert count == 0
    assert config_path.stat().st_mtime == mtime_before


def test_returns_zero_when_meta_is_empty_file(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    meta_path.write_text("")

    count = restore_clients(config_path, meta_path)

    assert count == 0


def test_returns_zero_when_meta_has_no_clients(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [])
    _write_meta(meta_path, {})

    count = restore_clients(config_path, meta_path)

    assert count == 0


def test_does_not_write_config_when_all_clients_already_present(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [{"id": "abc-123", "email": "msk-nb"}])
    _write_meta(meta_path, {"abc-123": {"name": "msk-nb", "short_id": "aabbccdd11223344"}})
    mtime_before = config_path.stat().st_mtime

    restore_clients(config_path, meta_path)

    assert config_path.stat().st_mtime == mtime_before


def test_partial_restore_when_some_clients_already_in_config(tmp_path: Path) -> None:
    config_path = tmp_path / "config.json"
    meta_path = tmp_path / "clients-meta.json"
    _write_config(config_path, [{"id": "abc-123", "email": "msk-nb"}])
    _write_meta(meta_path, {
        "abc-123": {"name": "msk-nb", "short_id": "aabbccdd11223344"},
        "def-456": {"name": "msk-iphone", "short_id": "eeff00112233aabb"},
    })

    count = restore_clients(config_path, meta_path)

    assert count == 1
    config = _read_config(config_path)
    inbound = next(i for i in config["inbounds"] if i["tag"] == "frontend-in")
    ids = {c["id"] for c in inbound["settings"]["clients"]}
    assert ids == {"abc-123", "def-456"}
