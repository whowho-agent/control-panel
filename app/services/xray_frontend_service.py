import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any
from urllib.parse import quote, urlencode

from app.domain.xray_frontend import (
    ControlPlaneError,
    CreateFrontendClientCommand,
    FrontendClient,
    FrontendClientUriResult,
    TopologyHealthResult,
)
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand
from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo


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
        self.transport_mode = (transport_mode or "direct").strip().lower()
        self.relay_public_host = relay_public_host
        self.relay_private_host = relay_private_host
        self.ipsec_local_tunnel_ip = ipsec_local_tunnel_ip
        self.ipsec_remote_tunnel_ip = ipsec_remote_tunnel_ip
        self._topology_cache: dict[str, Any] = {"value": None, "expires_at": None}

    def list_clients(self) -> list[FrontendClient]:
        config = self.frontend_repo.read_config()
        meta = self.meta_repo.read()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        activity = self._parse_activity()
        now = datetime.now(timezone.utc)
        clients: list[FrontendClient] = []
        meta_changed = False
        enabled_client_ids = [
            item["id"] for item in inbound["settings"].get("clients", []) if item.get("enable", True)
        ]

        fallback_activity = None
        if len(enabled_client_ids) == 1 and activity:
            fallback_activity = max(activity.values(), key=lambda item: item["last_seen_dt"])

        for item in inbound["settings"].get("clients", []):
            client_id = item["id"]
            client_meta = meta.get("clients", {}).get(client_id, {})
            last_seen = client_meta.get("last_seen", "")
            source_ip = client_meta.get("source_ip", "")
            matched_activity = activity.get(source_ip) if source_ip else None

            if matched_activity:
                last_seen = matched_activity["last_seen"]
                source_ip = matched_activity["source_ip"]
                if client_meta.get("last_seen") != last_seen or client_meta.get("source_ip") != source_ip:
                    meta.setdefault("clients", {}).setdefault(client_id, {}).update(
                        {"last_seen": last_seen, "source_ip": source_ip}
                    )
                    meta_changed = True
            elif fallback_activity and client_id == enabled_client_ids[0]:
                last_seen = fallback_activity["last_seen"]
                source_ip = fallback_activity["source_ip"]
                if client_meta.get("last_seen") != last_seen or client_meta.get("source_ip") != source_ip:
                    meta.setdefault("clients", {}).setdefault(client_id, {}).update(
                        {"last_seen": last_seen, "source_ip": source_ip}
                    )
                    meta_changed = True

            status = "offline"
            if last_seen:
                seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if now - seen_dt <= timedelta(minutes=self.online_window_minutes):
                    status = "online"
            elif activity and item.get("enable", True):
                status = "activity-unattributed"
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

        if meta_changed:
            self.meta_repo.write(meta)
        return clients

    def create_client(self, command: CreateFrontendClientCommand) -> FrontendClientUriResult:
        name = command.name.strip()
        host = command.host.strip()
        if not name:
            raise ControlPlaneError("client_name_empty", "Client name must not be empty")
        if not host:
            raise ControlPlaneError("client_host_empty", "Client host must not be empty")

        config = self.frontend_repo.read_config()
        frontend = self.frontend_repo.get_frontend_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        reality = inbound["streamSettings"]["realitySettings"]
        existing_emails = {
            item.get("email", "").strip().casefold()
            for item in inbound["settings"].get("clients", [])
            if item.get("email")
        }
        if name.casefold() in existing_emails:
            raise ControlPlaneError("client_name_exists", f"Client '{name}' already exists", status_code=409)

        client_id = str(uuid.uuid4())
        short_id = self._generate_short_id(frontend.short_ids)
        reality.setdefault("shortIds", [])
        if short_id not in reality["shortIds"]:
            reality["shortIds"].append(short_id)
        inbound["settings"].setdefault("clients", []).append({"id": client_id, "email": name})
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_create_apply_failed",
                f"Client was not created because frontend apply failed: {apply_result.message}",
                status_code=409,
            )

        meta = self.meta_repo.read()
        meta.setdefault("clients", {})[client_id] = {
            "name": name,
            "short_id": short_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "last_seen": "",
            "source_ip": "",
        }
        self.meta_repo.write(meta)

        client = FrontendClient(id=client_id, name=name, short_id=short_id, email=name)
        frontend.short_ids = reality["shortIds"]
        uri = self.build_client_uri(host, client, frontend)
        return FrontendClientUriResult(client=client, uri=uri)

    def delete_client(self, client_id: str) -> bool:
        config = self.frontend_repo.read_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        before = len(inbound["settings"].get("clients", []))
        inbound["settings"]["clients"] = [
            item
            for item in inbound["settings"].get("clients", [])
            if item.get("id") != client_id
        ]
        if len(inbound["settings"]["clients"]) == before:
            return False
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_delete_apply_failed",
                f"Client delete aborted because frontend apply failed: {apply_result.message}",
                status_code=409,
            )
        meta = self.meta_repo.read()
        meta.get("clients", {}).pop(client_id, None)
        self.meta_repo.write(meta)
        return True

    def set_client_enabled(self, client_id: str, enabled: bool) -> bool:
        config = self.frontend_repo.read_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        target = next(
            (item for item in inbound["settings"].get("clients", []) if item.get("id") == client_id),
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
        ipsec_expected = self.transport_mode == "ipsec"
        active_relay_host = frontend.relay_host
        ipsec_active = bool(
            ipsec_expected
            and self.relay_private_host
            and active_relay_host == self.relay_private_host
            and self.relay_repo.is_port_reachable()
        )
        relay_reachable = self.relay_repo.is_port_reachable()
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
            transport_mode=self.transport_mode,
            transport_label=self._transport_label(ipsec_expected, ipsec_active),
            relay_public_host=self.relay_public_host,
            relay_private_host=self.relay_private_host,
            active_relay_host=active_relay_host,
            active_relay_port=frontend.relay_port,
            ipsec_expected=ipsec_expected,
            ipsec_active=ipsec_active,
            ipsec_local_tunnel_ip=self.ipsec_local_tunnel_ip,
            ipsec_remote_tunnel_ip=self.ipsec_remote_tunnel_ip,
        )
        self._topology_cache = {
            "value": result,
            "expires_at": now + timedelta(seconds=self.topology_cache_ttl_seconds),
        }
        return result

    def get_frontend_config(self):
        return self.frontend_repo.get_frontend_config()

    def get_relay_config(self):
        return self.frontend_repo.get_relay_config_from_frontend()

    def validate_frontend_config(self, command: UpdateFrontendConfigCommand):
        config = self.read_candidate_frontend_config(command)
        return self.frontend_repo.validate_config(config)

    def validate_relay_config(self, command: UpdateRelayConfigCommand):
        config = self.read_candidate_relay_config(command)
        return self.frontend_repo.validate_config(config)

    def update_frontend_config(self, command: UpdateFrontendConfigCommand):
        config = self.read_candidate_frontend_config(command)
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "frontend_apply_failed",
                f"Frontend config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self.frontend_repo.get_frontend_config()

    def update_relay_config(self, command: UpdateRelayConfigCommand):
        config = self.read_candidate_relay_config(command)
        apply_result = self.frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "relay_apply_failed",
                f"Relay config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self.frontend_repo.get_relay_config_from_frontend()

    def read_candidate_frontend_config(self, command: UpdateFrontendConfigCommand) -> dict:
        config = self.frontend_repo.read_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        outbound = next(item for item in config["outbounds"] if item.get("tag") == "to-relay")
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
        outbound["settings"]["vnext"][0]["address"] = command.relay_host
        outbound["settings"]["vnext"][0]["port"] = command.relay_port
        return config

    def read_candidate_relay_config(self, command: UpdateRelayConfigCommand) -> dict:
        config = self.frontend_repo.read_config()
        outbound = next(item for item in config["outbounds"] if item.get("tag") == "to-relay")
        outbound["settings"]["vnext"][0]["address"] = command.public_host
        outbound["settings"]["vnext"][0]["port"] = command.listen_port
        outbound["settings"]["vnext"][0]["users"][0]["id"] = command.relay_uuid
        return config

    def build_client_uri(self, host: str, client: FrontendClient, frontend_config) -> str:
        query = {
            "type": "tcp",
            "security": "reality",
            "pbk": frontend_config.public_key,
            "fp": frontend_config.fingerprint,
            "sni": frontend_config.server_name,
            "sid": client.short_id or (frontend_config.short_ids[0] if frontend_config.short_ids else ""),
            "spx": frontend_config.spider_x,
            "encryption": "none",
        }
        return (
            f"vless://{client.id}@{host}:{frontend_config.port}?"
            f"{urlencode(query)}#{quote(client.name)}"
        )

    def _generate_short_id(self, existing_short_ids: list[str]) -> str:
        existing = set(existing_short_ids)
        while True:
            short_id = secrets.token_hex(8)
            if short_id not in existing:
                return short_id

    def _transport_label(self, ipsec_expected: bool, ipsec_active: bool) -> str:
        if not ipsec_expected:
            return "Direct public relay"
        if ipsec_active:
            return "IPSec private relay"
        return "IPSec configured, waiting for private cutover"

    def _parse_activity(self) -> dict[str, dict[str, Any]]:
        result: dict[str, dict[str, Any]] = {}
        if not self.frontend_repo.access_log_path.exists():
            return result
        line_re = re.compile(
            r"^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+) "
            r"from (?P<ip>[^:]+):\d+ accepted .*? \[(?P<inbound>[^\]]+) ->"
        )
        lines = self.frontend_repo.access_log_path.read_text(errors="ignore").splitlines()[-2000:]
        for line in lines:
            match = line_re.search(line)
            if not match or match.group("inbound") != "frontend-in":
                continue
            seen_at = datetime.strptime(match.group("ts"), "%Y/%m/%d %H:%M:%S.%f").replace(
                tzinfo=timezone.utc
            )
            ip = match.group("ip")
            previous = result.get(ip)
            if not previous or seen_at > previous["last_seen_dt"]:
                result[ip] = {
                    "last_seen_dt": seen_at,
                    "last_seen": seen_at.isoformat().replace("+00:00", "Z"),
                    "source_ip": ip,
                }
        return result
