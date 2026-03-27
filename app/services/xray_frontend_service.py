import logging
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from app.domain.client_status import compute_status
from app.domain.transport_mode import TransportMode
from app.domain.vless_uri import VlessUriBuilder
from app.domain.xray_config import XrayConfigAccessor
from app.domain.xray_frontend import (
    ControlPlaneError,
    CreateFrontendClientCommand,
    FrontendApplyResult,
    FrontendClient,
    FrontendClientUriResult,
    FrontendConfigResult,
    RelayConfigResult,
    TopologyHealthResult,
)
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand
from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo

logger = logging.getLogger(__name__)


class XrayFrontendService:
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
        self.frontend_repo = frontend_repo
        self.meta_repo = meta_repo
        self.relay_repo = relay_repo
        self.online_window_minutes = online_window_minutes
        self.expected_egress_ip = expected_egress_ip
        self.topology_cache_ttl_seconds = topology_cache_ttl_seconds
        self._transport_mode = TransportMode.from_string(transport_mode)
        self.relay_public_host = relay_public_host
        self.relay_private_host = relay_private_host
        self.ipsec_local_tunnel_ip = ipsec_local_tunnel_ip
        self.ipsec_remote_tunnel_ip = ipsec_remote_tunnel_ip
        self._topology_cache: dict[str, Any] = {"value": None, "expires_at": None}

    def list_clients(self) -> list[FrontendClient]:
        activity = self.frontend_repo.parse_activity()
        clients, meta, meta_changed = self._build_clients(activity)
        if meta_changed:
            self.meta_repo.write(meta)
        return clients

    def _build_clients(self, activity: dict) -> tuple[list[FrontendClient], dict, bool]:
        config = self.frontend_repo.read_config()
        meta = self.meta_repo.read()
        clients: list[FrontendClient] = []
        meta_changed = False
        enabled_client_ids = [
            item["id"] for item in config.frontend_clients() if item.get("enable", True)
        ]

        fallback_activity = None
        if len(enabled_client_ids) == 1 and activity:
            fallback_activity = max(activity.values(), key=lambda item: item["last_seen_dt"])

        for item in config.frontend_clients():
            client_id = item["id"]
            client_meta = meta.get("clients", {}).get(client_id, {})
            last_seen = client_meta.get("last_seen", "")
            source_ip = client_meta.get("source_ip", "")
            matched_activity = activity.get(source_ip) if source_ip else None

            if matched_activity:
                last_seen = matched_activity["last_seen"]
                source_ip = matched_activity["source_ip"]
                if client_meta.get("last_seen") != last_seen or client_meta.get("source_ip") != source_ip:
                    meta = _update_client_meta(meta, client_id, last_seen, source_ip)
                    meta_changed = True
            elif fallback_activity and client_id == enabled_client_ids[0]:
                last_seen = fallback_activity["last_seen"]
                source_ip = fallback_activity["source_ip"]
                if client_meta.get("last_seen") != last_seen or client_meta.get("source_ip") != source_ip:
                    meta = _update_client_meta(meta, client_id, last_seen, source_ip)
                    meta_changed = True

            status = compute_status(
                last_seen=last_seen,
                enabled=item.get("enable", True),
                has_any_activity=bool(activity),
                window_minutes=self.online_window_minutes,
            )
            clients.append(
                FrontendClient(
                    id=client_id,
                    name=client_meta.get("name") or item.get("email") or client_id,
                    short_id=client_meta.get("short_id", ""),
                    email=item.get("email", ""),
                    created_at=client_meta.get("created_at", ""),
                    last_seen=last_seen,
                    source_ip=source_ip,
                    status=status,
                    enabled=item.get("enable", True),
                )
            )

        return clients, meta, meta_changed

    def create_client(self, command: CreateFrontendClientCommand) -> FrontendClientUriResult:
        name = command.name.strip()
        host = command.host.strip()
        if not name:
            raise ControlPlaneError("client_name_empty", "Client name must not be empty")
        if not host:
            raise ControlPlaneError("client_host_empty", "Client host must not be empty")

        config = self.frontend_repo.read_config()
        frontend = self.frontend_repo.get_frontend_config()
        reality = config.frontend_inbound()["streamSettings"]["realitySettings"]
        existing_emails = {
            item.get("email", "").strip().casefold()
            for item in config.frontend_clients()
            if item.get("email")
        }
        if name.casefold() in existing_emails:
            raise ControlPlaneError("client_name_exists", f"Client '{name}' already exists", status_code=409)

        client_id = str(uuid.uuid4())
        short_id = self._generate_short_id(frontend.short_ids)
        reality.setdefault("shortIds", [])
        if short_id not in reality["shortIds"]:
            reality["shortIds"].append(short_id)
        config.set_frontend_clients([*config.frontend_clients(), {"id": client_id, "email": name}])
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_create_apply_failed",
                f"Client was not created because frontend apply failed: {apply_result.message}",
                status_code=409,
            )

        meta = self.meta_repo.read()
        new_entry = {
            "name": name,
            "short_id": short_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "last_seen": "",
            "source_ip": "",
        }
        self.meta_repo.write({**meta, "clients": {**meta.get("clients", {}), client_id: new_entry}})

        client = FrontendClient(id=client_id, name=name, short_id=short_id, email=name)
        frontend.short_ids = reality["shortIds"]
        uri = self.build_client_uri(host, client, frontend)
        return FrontendClientUriResult(client=client, uri=uri)

    def delete_client(self, client_id: str) -> bool:
        config = self.frontend_repo.read_config()
        before = len(config.frontend_clients())
        config.set_frontend_clients([item for item in config.frontend_clients() if item.get("id") != client_id])
        if len(config.frontend_clients()) == before:
            return False
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_delete_apply_failed",
                f"Client delete aborted because frontend apply failed: {apply_result.message}",
                status_code=409,
            )
        meta = self.meta_repo.read()
        remaining = {k: v for k, v in meta.get("clients", {}).items() if k != client_id}
        self.meta_repo.write({**meta, "clients": remaining})
        return True

    def set_client_enabled(self, client_id: str, enabled: bool) -> bool:
        config = self.frontend_repo.read_config()
        target = next(
            (item for item in config.frontend_clients() if item.get("id") == client_id),
            None,
        )
        if target is None:
            return False
        target["enable"] = enabled
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_toggle_apply_failed",
                f"Client state change aborted because frontend apply failed: {apply_result.message}",
                status_code=409,
            )
        return True

    def get_topology_health(self) -> TopologyHealthResult:
        now = datetime.now(timezone.utc)
        expires_at = self._topology_cache.get("expires_at")
        cached_value = self._topology_cache.get("value")
        if cached_value is not None and expires_at is not None and now < expires_at:
            return cached_value

        clients = self.list_clients()
        frontend = self.frontend_repo.get_frontend_config()
        observed_egress_ip = self.relay_repo.probe_observed_public_ip()
        readiness = self.frontend_repo.get_frontend_readiness()
        active_relay_host = frontend.relay_host
        relay_reachable = self.relay_repo.is_port_reachable()
        ipsec_active = bool(
            self._transport_mode.is_ipsec
            and self.relay_private_host
            and active_relay_host == self.relay_private_host
            and relay_reachable
        )
        result = TopologyHealthResult(
            frontend_service=self.frontend_repo.get_frontend_service_status(),
            relay_service=self.relay_repo.get_remote_service_status(),
            relay_reachable=relay_reachable,
            expected_egress_ip=self.expected_egress_ip,
            client_count=len(clients),
            online_count=sum(1 for item in clients if item.status == "online"),
            egress_probe_ok=bool(observed_egress_ip) and observed_egress_ip == self.expected_egress_ip,
            observed_egress_ip=observed_egress_ip,
            frontend_ready=readiness.ready,
            frontend_readiness_status=readiness.status,
            transport_mode=self._transport_mode.mode,
            transport_label=self._transport_mode.label(ipsec_active, bool(self.relay_private_host)),
            relay_public_host=self.relay_public_host,
            relay_private_host=self.relay_private_host,
            active_relay_host=active_relay_host,
            active_relay_port=frontend.relay_port,
            ipsec_expected=self._transport_mode.is_ipsec,
            ipsec_active=ipsec_active,
            ipsec_local_tunnel_ip=self.ipsec_local_tunnel_ip,
            ipsec_remote_tunnel_ip=self.ipsec_remote_tunnel_ip,
        )
        self._topology_cache = {
            "value": result,
            "expires_at": now + timedelta(seconds=self.topology_cache_ttl_seconds),
        }
        return result

    def get_frontend_config(self) -> FrontendConfigResult:
        return self.frontend_repo.get_frontend_config()

    def get_relay_config(self) -> RelayConfigResult:
        return self.frontend_repo.get_relay_config_from_frontend()

    def validate_frontend_config(self, command: UpdateFrontendConfigCommand) -> FrontendApplyResult:
        config = self.read_candidate_frontend_config(command)
        return self.frontend_repo.validate_config(config)

    def validate_relay_config(self, command: UpdateRelayConfigCommand) -> FrontendApplyResult:
        config = self.read_candidate_relay_config(command)
        return self.frontend_repo.validate_config(config)

    def update_frontend_config(self, command: UpdateFrontendConfigCommand) -> FrontendConfigResult:
        config = self.read_candidate_frontend_config(command)
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "frontend_apply_failed",
                f"Frontend config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self.frontend_repo.get_frontend_config()

    def update_relay_config(self, command: UpdateRelayConfigCommand) -> RelayConfigResult:
        config = self.read_candidate_relay_config(command)
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "relay_apply_failed",
                f"Relay config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self.frontend_repo.get_relay_config_from_frontend()

    def read_candidate_frontend_config(self, command: UpdateFrontendConfigCommand) -> XrayConfigAccessor:
        config = self.frontend_repo.read_config()
        inbound = config.frontend_inbound()
        vnext = config.relay_outbound()["settings"]["vnext"][0]
        reality = inbound["streamSettings"]["realitySettings"]
        inbound["port"] = command.port
        reality["target"] = command.target
        reality["dest"] = command.target
        reality["serverNames"] = [command.server_name]
        reality.pop("serverName", None)
        reality["fingerprint"] = command.fingerprint
        reality["spiderX"] = command.spider_x
        reality.setdefault("settings", {})["fingerprint"] = command.fingerprint
        reality.setdefault("settings", {})["spiderX"] = command.spider_x
        reality["shortIds"] = command.short_ids
        vnext["address"] = command.relay_host
        vnext["port"] = command.relay_port
        return config

    def read_candidate_relay_config(self, command: UpdateRelayConfigCommand) -> XrayConfigAccessor:
        config = self.frontend_repo.read_config()
        vnext = config.relay_outbound()["settings"]["vnext"][0]
        vnext["address"] = command.public_host
        vnext["port"] = command.listen_port
        vnext["users"][0]["id"] = command.relay_uuid
        return config

    def build_client_uri(self, host: str, client: FrontendClient, frontend_config: FrontendConfigResult) -> str:
        return VlessUriBuilder().build(client, host, frontend_config)

    def _generate_short_id(self, existing_short_ids: list[str]) -> str:
        existing = set(existing_short_ids)
        for _ in range(100):
            short_id = secrets.token_hex(8)
            if short_id not in existing:
                return short_id
        raise RuntimeError("Failed to generate a unique short_id after 100 attempts")


def _update_client_meta(meta: dict, client_id: str, last_seen: str, source_ip: str) -> dict:
    updated_client = {**meta.get("clients", {}).get(client_id, {}), "last_seen": last_seen, "source_ip": source_ip}
    return {**meta, "clients": {**meta.get("clients", {}), client_id: updated_client}}
