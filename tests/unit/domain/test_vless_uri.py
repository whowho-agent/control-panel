from urllib.parse import parse_qs, quote, urlparse

from app.domain.vless_uri import VlessUriBuilder
from app.domain.xray_frontend import FrontendClient, FrontendConfigResult


def make_client(
    id: str = "abc123",
    name: str = "Test User",
    short_id: str = "deadbeef",
) -> FrontendClient:
    return FrontendClient(
        id=id,
        name=name,
        short_id=short_id,
    )


def make_config(
    port: int = 443,
    public_key: str = "pubkey1",
    fingerprint: str = "chrome",
    server_name: str = "example.com",
    short_ids: list[str] | None = None,
    spider_x: str = "/",
) -> FrontendConfigResult:
    return FrontendConfigResult(
        port=port,
        server_name=server_name,
        public_key=public_key,
        private_key="privkey1",
        fingerprint=fingerprint,
        short_ids=short_ids if short_ids is not None else ["cfgshortid"],
        spider_x=spider_x,
        target="target.example.com",
        relay_host="relay.example.com",
        relay_port=8443,
        relay_uuid="relay-uuid",
    )


def parse_uri(uri: str):
    """Return (parsed_url, query_params_dict) for a vless:// URI."""
    parsed = urlparse(uri)
    params = parse_qs(parsed.query)
    return parsed, {k: v[0] for k, v in params.items()}


builder = VlessUriBuilder()


def test_build_produces_vless_scheme():
    uri = builder.build(make_client(), "1.2.3.4", make_config())
    assert uri.startswith("vless://")


def test_build_encodes_client_id_and_host():
    client = make_client(id="client-uuid-001")
    config = make_config(port=8443)
    uri = builder.build(client, "10.0.0.1", config)
    assert "client-uuid-001@10.0.0.1:8443" in uri


def test_build_uses_short_id_from_client():
    client = make_client(short_id="clientsid")
    config = make_config(short_ids=["cfgsid1", "cfgsid2"])
    uri = builder.build(client, "1.2.3.4", config)
    _, params = parse_uri(uri)
    assert params["sid"] == "clientsid"


def test_build_falls_back_to_first_config_short_id_when_client_short_id_empty():
    client = make_client(short_id="")
    config = make_config(short_ids=["first-cfg-sid", "second-cfg-sid"])
    uri = builder.build(client, "1.2.3.4", config)
    _, params = parse_uri(uri)
    assert params["sid"] == "first-cfg-sid"


def test_build_sid_empty_when_no_short_ids_available():
    client = make_client(short_id="")
    config = make_config(short_ids=[])
    uri = builder.build(client, "1.2.3.4", config)
    _, params = parse_uri(uri)
    assert params.get("sid", "") == ""


def test_build_encodes_client_name_in_fragment():
    client = make_client(name="My Client / Test")
    uri = builder.build(client, "1.2.3.4", make_config())
    parsed = urlparse(uri)
    assert parsed.fragment == quote("My Client / Test")


def test_build_includes_all_reality_params():
    config = make_config(
        public_key="mypubkey",
        fingerprint="firefox",
        server_name="sni.example.com",
        spider_x="/path",
    )
    uri = builder.build(make_client(), "1.2.3.4", config)
    _, params = parse_uri(uri)
    assert params["security"] == "reality"
    assert params["pbk"] == "mypubkey"
    assert params["fp"] == "firefox"
    assert params["sni"] == "sni.example.com"
    assert params["spx"] == "/path"
    assert params["encryption"] == "none"
    assert params["type"] == "tcp"
