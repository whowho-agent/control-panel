import functools
import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable, TypeVar

from app.domain.transport_mode import TransportMode
from app.domain.xray_frontend import TopologyHealthResult
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo
from app.services.client_service import ClientService

logger = logging.getLogger(__name__)

F = TypeVar("F", bound=Callable[..., Any])


def ttl_cache(seconds: int = 10) -> Callable[[F], F]:
    """TTL cache decorator for instance methods.

    Reads ``self._ttl_seconds`` at call time if present, falling back to the
    ``seconds`` argument supplied at decoration time.
    """

    def decorator(func: F) -> F:
        cache_attr = f"_ttl_cache_{func.__name__}"

        @functools.wraps(func)
        def wrapper(self: Any, *args: Any, **kwargs: Any) -> Any:
            now = datetime.now(timezone.utc)
            ttl = getattr(self, "_ttl_seconds", seconds)
            cached: dict[str, Any] = getattr(self, cache_attr, {"value": None, "expires_at": None})
            if cached["value"] is not None and cached["expires_at"] is not None and now < cached["expires_at"]:
                return cached["value"]
            result = func(self, *args, **kwargs)
            setattr(self, cache_attr, {"value": result, "expires_at": now + timedelta(seconds=ttl)})
            return result

        return wrapper  # type: ignore[return-value]

    return decorator


class TopologyService:
    def __init__(
        self,
        frontend_repo: XrayFrontendRepo,
        relay_repo: RelayNodeRepo,
        client_service: ClientService,
        expected_egress_ip: str,
        ttl_seconds: int,
        transport_mode: TransportMode,
        relay_public_host: str = "",
        relay_private_host: str = "",
        ipsec_local_tunnel_ip: str = "",
        ipsec_remote_tunnel_ip: str = "",
    ) -> None:
        self._frontend_repo = frontend_repo
        self._relay_repo = relay_repo
        self._client_service = client_service
        self._expected_egress_ip = expected_egress_ip
        self._ttl_seconds = ttl_seconds
        self._transport_mode = transport_mode
        self._relay_public_host = relay_public_host
        self._relay_private_host = relay_private_host
        self._ipsec_local_tunnel_ip = ipsec_local_tunnel_ip
        self._ipsec_remote_tunnel_ip = ipsec_remote_tunnel_ip

    @ttl_cache(seconds=10)
    def get(self) -> TopologyHealthResult:
        clients = self._client_service.list()
        frontend = self._frontend_repo.get_frontend_config()
        observed_egress_ip = self._relay_repo.probe_observed_public_ip()
        readiness = self._frontend_repo.get_frontend_readiness()
        active_relay_host = frontend.relay_host
        relay_reachable = self._relay_repo.is_port_reachable()
        ipsec_active = bool(
            self._transport_mode.is_ipsec
            and self._relay_private_host
            and active_relay_host == self._relay_private_host
            and relay_reachable
        )
        return TopologyHealthResult(
            frontend_service=self._frontend_repo.get_frontend_service_status(),
            relay_service=self._relay_repo.get_remote_service_status(),
            relay_reachable=relay_reachable,
            expected_egress_ip=self._expected_egress_ip,
            client_count=len(clients),
            online_count=sum(1 for item in clients if item.status == "online"),
            egress_probe_ok=bool(observed_egress_ip) and observed_egress_ip == self._expected_egress_ip,
            observed_egress_ip=observed_egress_ip,
            frontend_ready=readiness.ready,
            frontend_readiness_status=readiness.status,
            transport_mode=self._transport_mode.mode,
            transport_label=self._transport_mode.label(ipsec_active, bool(self._relay_private_host)),
            relay_public_host=self._relay_public_host,
            relay_private_host=self._relay_private_host,
            active_relay_host=active_relay_host,
            active_relay_port=frontend.relay_port,
            ipsec_expected=self._transport_mode.is_ipsec,
            ipsec_active=ipsec_active,
            ipsec_local_tunnel_ip=self._ipsec_local_tunnel_ip,
            ipsec_remote_tunnel_ip=self._ipsec_remote_tunnel_ip,
        )
