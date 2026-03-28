import pytest

from app.domain.xray_config import XrayConfigAccessor


def _make_config(
    inbound_tag: str = "frontend-in",
    outbound_tag: str = "to-relay",
    clients: list | None = None,
) -> dict:
    return {
        "inbounds": [
            {
                "tag": inbound_tag,
                "port": 9444,
                "settings": {"clients": clients or [{"id": "c1"}]},
                "streamSettings": {"realitySettings": {"shortIds": ["aa"]}},
            }
        ],
        "outbounds": [
            {
                "tag": outbound_tag,
                "settings": {"vnext": [{"address": "1.2.3.4", "port": 9443, "users": [{"id": "uuid1"}]}]},
            }
        ],
    }


def test_frontend_inbound_returns_correct_inbound() -> None:
    acc = XrayConfigAccessor(_make_config())
    assert acc.frontend_inbound()["tag"] == "frontend-in"
    assert acc.frontend_inbound()["port"] == 9444


def test_relay_outbound_returns_correct_outbound() -> None:
    acc = XrayConfigAccessor(_make_config())
    assert acc.relay_outbound()["tag"] == "to-relay"
    assert acc.relay_outbound()["settings"]["vnext"][0]["address"] == "1.2.3.4"


def test_frontend_clients_returns_client_list() -> None:
    acc = XrayConfigAccessor(_make_config(clients=[{"id": "c1"}, {"id": "c2"}]))
    assert acc.frontend_clients() == [{"id": "c1"}, {"id": "c2"}]


def test_frontend_clients_returns_empty_list_when_key_absent() -> None:
    raw = _make_config()
    del raw["inbounds"][0]["settings"]["clients"]
    acc = XrayConfigAccessor(raw)
    assert acc.frontend_clients() == []


def test_set_frontend_clients_replaces_list() -> None:
    acc = XrayConfigAccessor(_make_config())
    acc.set_frontend_clients([{"id": "new"}])
    assert acc.frontend_clients() == [{"id": "new"}]


def test_set_frontend_clients_mutation_reflected_in_to_dict() -> None:
    acc = XrayConfigAccessor(_make_config())
    acc.set_frontend_clients([{"id": "x"}])
    raw = acc.to_dict()
    inbound = next(item for item in raw["inbounds"] if item["tag"] == "frontend-in")
    assert inbound["settings"]["clients"] == [{"id": "x"}]


def test_to_dict_returns_deep_copy() -> None:
    raw = _make_config()
    acc = XrayConfigAccessor(raw)
    result = acc.to_dict()
    assert result == raw
    assert result is not raw  # must be a copy, not the internal reference


def test_frontend_inbound_raises_key_error_when_tag_missing() -> None:
    acc = XrayConfigAccessor(_make_config(inbound_tag="other-tag"))
    with pytest.raises(KeyError, match="frontend-in"):
        acc.frontend_inbound()


def test_relay_outbound_raises_key_error_when_tag_missing() -> None:
    acc = XrayConfigAccessor(_make_config(outbound_tag="other-tag"))
    with pytest.raises(KeyError, match="to-relay"):
        acc.relay_outbound()


def test_config_with_multiple_inbounds_finds_correct_one() -> None:
    raw = _make_config()
    raw["inbounds"].insert(0, {"tag": "other-in", "port": 1234, "settings": {}})
    acc = XrayConfigAccessor(raw)
    assert acc.frontend_inbound()["port"] == 9444


def test_config_with_multiple_outbounds_finds_correct_one() -> None:
    raw = _make_config()
    raw["outbounds"].append({"tag": "direct", "settings": {}})
    acc = XrayConfigAccessor(raw)
    assert acc.relay_outbound()["settings"]["vnext"][0]["port"] == 9443
