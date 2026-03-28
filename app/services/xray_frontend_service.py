from app.domain.activity_log import ActivityLogEntry
from app.domain.transport_mode import TransportMode
from app.domain.xray_frontend import (
    CreateFrontendClientCommand,
    FrontendApplyResult,
    FrontendClient,
    FrontendClientUriResult,
    FrontendConfigResult,
    RelayConfigResult,
    SniffingConfigResult,
    TopologyHealthResult,
)
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand, UpdateSniffingCommand
from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo
from app.services.client_service import ClientService
from app.services.config_service import ConfigService
from app.services.topology_service import TopologyService


class XrayFrontendService:
    """Facade: API layer depends only on this class; all logic lives in sub-services."""

    def __init__(
        self,
        frontend_repo: XrayFrontendRepo,
        meta_repo: ClientMetaRepo,
        relay_repo: RelayNodeRepo,
        online_window_minutes: int,
        expected_egress_ip: str,
        topology_cache_ttl_seconds: int,
        transport_mode: str = "direct",
        relay_public_host: str = "",
        relay_private_host: str = "",
        ipsec_local_tunnel_ip: str = "",
        ipsec_remote_tunnel_ip: str = "",
    ) -> None:
        tm = TransportMode.from_string(transport_mode)
        self._clients = ClientService(frontend_repo, meta_repo, online_window_minutes)
        self._config = ConfigService(frontend_repo)
        self._topology = TopologyService(
            frontend_repo=frontend_repo,
            relay_repo=relay_repo,
            client_service=self._clients,
            expected_egress_ip=expected_egress_ip,
            ttl_seconds=topology_cache_ttl_seconds,
            transport_mode=tm,
            relay_public_host=relay_public_host,
            relay_private_host=relay_private_host,
            ipsec_local_tunnel_ip=ipsec_local_tunnel_ip,
            ipsec_remote_tunnel_ip=ipsec_remote_tunnel_ip,
        )

    # --- clients ---

    def list_clients(self) -> list[FrontendClient]:
        return self._clients.list()

    def create_client(self, command: CreateFrontendClientCommand) -> FrontendClientUriResult:
        return self._clients.create(command)

    def delete_client(self, client_id: str) -> bool:
        return self._clients.delete(client_id)

    def set_client_enabled(self, client_id: str, enabled: bool) -> FrontendClient | None:
        return self._clients.set_enabled(client_id, enabled)

    def build_client_uri(self, host: str, client: FrontendClient, frontend_config: FrontendConfigResult) -> str:
        return self._clients.build_uri(host, client, frontend_config)

    # --- topology ---

    def get_topology_health(self) -> TopologyHealthResult:
        return self._topology.get()

    # --- config ---

    def get_frontend_config(self) -> FrontendConfigResult:
        return self._config.get_frontend()

    def get_relay_config(self) -> RelayConfigResult:
        return self._config.get_relay()

    def validate_frontend_config(self, command: UpdateFrontendConfigCommand) -> FrontendApplyResult:
        return self._config.validate_frontend(command)

    def validate_relay_config(self, command: UpdateRelayConfigCommand) -> FrontendApplyResult:
        return self._config.validate_relay(command)

    def update_frontend_config(self, command: UpdateFrontendConfigCommand) -> FrontendConfigResult:
        return self._config.update_frontend(command)

    def update_relay_config(self, command: UpdateRelayConfigCommand) -> RelayConfigResult:
        return self._config.update_relay(command)

    def get_recent_activity(self, minutes: int, limit: int = 100) -> list[ActivityLogEntry]:
        return self._clients.get_recent_activity(minutes, limit=limit)

    def get_sniffing_config(self) -> SniffingConfigResult:
        return self._config.get_sniffing()

    def update_sniffing_config(self, command: UpdateSniffingCommand) -> SniffingConfigResult:
        return self._config.update_sniffing(command)
