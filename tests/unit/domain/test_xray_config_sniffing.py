from app.domain.xray_config import XrayConfigAccessor


def _make_config(sniffing: dict | None = None) -> dict:
    inbound: dict = {
        "tag": "frontend-in",
        "port": 9444,
        "settings": {"clients": []},
        "streamSettings": {},
    }
    if sniffing is not None:
        inbound["sniffing"] = sniffing
    return {
        "inbounds": [inbound],
        "outbounds": [{"tag": "to-relay", "settings": {"vnext": []}}],
    }


def test_get_sniffing_returns_defaults_when_key_absent() -> None:
    acc = XrayConfigAccessor(_make_config())
    result = acc.get_sniffing()
    assert result == {"enabled": False, "destOverride": [], "routeOnly": False}


def test_get_sniffing_returns_existing_values() -> None:
    raw = {"enabled": True, "destOverride": ["http", "tls"], "routeOnly": True}
    acc = XrayConfigAccessor(_make_config(sniffing=raw))
    result = acc.get_sniffing()
    assert result["enabled"] is True
    assert result["destOverride"] == ["http", "tls"]
    assert result["routeOnly"] is True


def test_set_sniffing_writes_correct_structure() -> None:
    acc = XrayConfigAccessor(_make_config())
    acc.set_sniffing(enabled=True, dest_override=["quic", "fakedns"], route_only=False)
    raw = acc.frontend_inbound()["sniffing"]
    assert raw == {"enabled": True, "destOverride": ["quic", "fakedns"], "routeOnly": False}


def test_set_sniffing_overwrites_existing_block() -> None:
    old = {"enabled": True, "destOverride": ["http"], "routeOnly": True}
    acc = XrayConfigAccessor(_make_config(sniffing=old))
    acc.set_sniffing(enabled=False, dest_override=[], route_only=False)
    raw = acc.frontend_inbound()["sniffing"]
    assert raw == {"enabled": False, "destOverride": [], "routeOnly": False}
