
from app.domain.transport_mode import TransportMode
from app.domain.xray_frontend import FrontendApplyResult, FrontendClient, FrontendConfigResult, TopologyHealthResult
from app.services.topology_service import TopologyService, ttl_cache

# --- ttl_cache decorator unit tests ---


class _Counted:
    def __init__(self, ttl: int = 10) -> None:
        self._ttl_seconds = ttl
        self.calls = 0

    @ttl_cache(seconds=10)
    def compute(self) -> int:
        self.calls += 1
        return self.calls


def test_ttl_cache_returns_cached_value_within_ttl() -> None:
    obj = _Counted()
    first = obj.compute()
    second = obj.compute()
    assert first == second == 1
    assert obj.calls == 1


def test_ttl_cache_recomputes_after_expiry() -> None:
    obj = _Counted(ttl=0)
    first = obj.compute()
    second = obj.compute()
    assert first == 1
    assert second == 2
    assert obj.calls == 2


def test_ttl_cache_reads_ttl_seconds_from_instance() -> None:
    obj = _Counted(ttl=0)
    obj.compute()
    obj.compute()
    assert obj.calls == 2


# --- TopologyService tests ---


class FakeFrontendRepo:
    def __init__(self, relay_host: str = "1.2.3.4") -> None:
        self._relay_host = relay_host

    def get_frontend_config(self) -> FrontendConfigResult:
        return FrontendConfigResult(
            port=9444,
            server_name="sn",
            public_key="pub",
            private_key="priv",
            fingerprint="ff",
            short_ids=[],
            spider_x="/",
            target="t",
            relay_host=self._relay_host,
            relay_port=9443,
            relay_uuid="uuid",
        )

    def get_frontend_service_status(self) -> str:
        return "active"

    def get_frontend_readiness(self) -> FrontendApplyResult:
        return FrontendApplyResult(True, False, True, "ready", "ok")


class FakeRelayRepo:
    def __init__(self, reachable: bool = True, status: str = "active", egress_ip: str = "9.9.9.9") -> None:
        self.reachable = reachable
        self.status = status
        self.egress_ip = egress_ip
        self.calls = 0

    def is_port_reachable(self, timeout: int = 2) -> bool:
        self.calls += 1
        return self.reachable

    def get_remote_service_status(self) -> str:
        self.calls += 1
        return self.status

    def probe_observed_public_ip(self) -> str:
        self.calls += 1
        return self.egress_ip


class FakeClientService:
    def list(self) -> list[FrontendClient]:
        return []


def _build_topology(
    transport_mode: str = "direct",
    relay_host: str = "9.9.9.9",
    relay_private_host: str = "10.0.0.2",
    reachable: bool = True,
    ttl: int = 10,
) -> tuple[TopologyService, FakeRelayRepo]:
    relay_repo = FakeRelayRepo(reachable=reachable, egress_ip="9.9.9.9")
    svc = TopologyService(
        frontend_repo=FakeFrontendRepo(relay_host=relay_host),
        relay_repo=relay_repo,
        client_service=FakeClientService(),
        expected_egress_ip="9.9.9.9",
        ttl_seconds=ttl,
        transport_mode=TransportMode.from_string(transport_mode),
        relay_public_host="9.9.9.9",
        relay_private_host=relay_private_host,
        ipsec_local_tunnel_ip="10.0.0.1",
        ipsec_remote_tunnel_ip="10.0.0.2",
    )
    return svc, relay_repo


def test_get_returns_topology_health() -> None:
    svc, _ = _build_topology()
    result = svc.get()
    assert isinstance(result, TopologyHealthResult)
    assert result.frontend_service == "active"
    assert result.relay_service == "active"
    assert result.egress_probe_ok is True
    assert result.transport_mode == "direct"
    assert result.transport_label == "Direct public relay"


def test_get_caches_within_ttl() -> None:
    svc, relay_repo = _build_topology()
    svc.get()
    svc.get()
    assert relay_repo.calls == 3  # probe_ip + is_reachable + service_status (first call only)


def test_get_ipsec_active_when_private_host_matches() -> None:
    svc, _ = _build_topology(transport_mode="ipsec", relay_host="10.0.0.2", reachable=True)
    result = svc.get()
    assert result.ipsec_active is True
    assert result.transport_label == "IPSec private relay"


def test_get_ipsec_degraded_when_unreachable() -> None:
    svc, _ = _build_topology(transport_mode="ipsec", relay_host="10.0.0.2", reachable=False)
    result = svc.get()
    assert result.ipsec_active is False
    assert result.transport_label == "IPSec degraded: private relay unreachable"


def test_get_ipsec_direct_mode_not_ipsec_active() -> None:
    svc, _ = _build_topology(transport_mode="direct", relay_host="10.0.0.2")
    result = svc.get()
    assert result.ipsec_active is False
    assert result.ipsec_expected is False
