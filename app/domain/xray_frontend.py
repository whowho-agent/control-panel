from dataclasses import dataclass, field


@dataclass(slots=True)
class FrontendClient:
    id: str
    name: str
    short_id: str
    email: str = ""
    created_at: str = ""
    last_seen: str = ""
    source_ip: str = ""
    status: str = "offline"
    enabled: bool = True


@dataclass(slots=True)
class CreateFrontendClientCommand:
    name: str
    host: str


@dataclass(slots=True)
class FrontendClientUriResult:
    client: FrontendClient
    uri: str


@dataclass(slots=True)
class FrontendConfigResult:
    port: int
    server_name: str
    public_key: str
    private_key: str
    fingerprint: str
    short_ids: list[str]
    spider_x: str
    target: str
    relay_host: str
    relay_port: int
    relay_uuid: str


@dataclass(slots=True)
class RelayConfigResult:
    host: str
    port: int
    uuid: str


@dataclass(slots=True)
class FrontendApplyResult:
    preflight_ok: bool
    restarted: bool
    ready: bool
    status: str
    message: str = ""
    rollback_performed: bool = False


@dataclass(slots=True)
class TopologyHealthResult:
    frontend_service: str
    relay_service: str
    relay_reachable: bool
    expected_egress_ip: str
    client_count: int
    online_count: int
    egress_probe_ok: bool = False
    observed_egress_ip: str = ""
    frontend_ready: bool = False
    frontend_readiness_status: str = "unknown"
    transport_mode: str = "direct"
    transport_label: str = "Direct public relay"
    relay_public_host: str = ""
    relay_private_host: str = ""
    active_relay_host: str = ""
    active_relay_port: int = 0
    ipsec_expected: bool = False
    ipsec_active: bool = False
    ipsec_local_tunnel_ip: str = ""
    ipsec_remote_tunnel_ip: str = ""


@dataclass(slots=True)
class ControlPlaneError(Exception):
    code: str
    message: str
    status_code: int = 400
    details: dict[str, str] = field(default_factory=dict)

    def __str__(self) -> str:
        return self.message
