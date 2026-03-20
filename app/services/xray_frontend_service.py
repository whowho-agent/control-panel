import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone

from app.domain.xray_frontend import CreateFrontendClientCommand, FrontendClient, FrontendClientUriResult, TopologyHealthResult
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
    ) -> None:
        self.frontend_repo = frontend_repo
        self.meta_repo = meta_repo
        self.relay_repo = relay_repo
        self.online_window_minutes = online_window_minutes
        self.expected_egress_ip = expected_egress_ip

    def list_clients(self) -> list[FrontendClient]:
        config = self.frontend_repo.read_config()
        meta = self.meta_repo.read()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        activity = self._parse_activity()
        latest = max(activity.values(), key=lambda item: item["last_seen_dt"]) if activity else None
        now = datetime.now(timezone.utc)
        clients: list[FrontendClient] = []
        for index, item in enumerate(inbound["settings"].get("clients", [])):
            client_id = item["id"]
            client_meta = meta.get("clients", {}).get(client_id, {})
            last_seen = client_meta.get("last_seen", "")
            source_ip = client_meta.get("source_ip", "")
            if not last_seen and index == 0 and latest:
                last_seen = latest["last_seen"]
                source_ip = latest["source_ip"]
            status = "offline"
            if last_seen:
                seen_dt = datetime.fromisoformat(last_seen.replace("Z", "+00:00"))
                if now - seen_dt <= timedelta(minutes=self.online_window_minutes):
                    status = "online"
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
                )
            )
        return clients

    def create_client(self, command: CreateFrontendClientCommand) -> FrontendClientUriResult:
        config = self.frontend_repo.read_config()
        frontend = self.frontend_repo.get_frontend_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        client_id = str(uuid.uuid4())
        short_id = secrets.choice(frontend.short_ids) if frontend.short_ids else ""
        inbound["settings"].setdefault("clients", []).append({"id": client_id})
        self.frontend_repo.write_config(config)

        meta = self.meta_repo.read()
        meta.setdefault("clients", {})[client_id] = {
            "name": command.name,
            "short_id": short_id,
            "created_at": datetime.utcnow().isoformat() + "Z",
            "last_seen": "",
            "source_ip": "",
        }
        self.meta_repo.write(meta)
        self.frontend_repo.restart_frontend()

        client = FrontendClient(id=client_id, name=command.name, short_id=short_id)
        uri = self.build_client_uri(command.host, client, frontend)
        return FrontendClientUriResult(client=client, uri=uri)

    def delete_client(self, client_id: str) -> bool:
        config = self.frontend_repo.read_config()
        inbound = next(item for item in config["inbounds"] if item.get("tag") == "frontend-in")
        before = len(inbound["settings"].get("clients", []))
        inbound["settings"]["clients"] = [item for item in inbound["settings"].get("clients", []) if item.get("id") != client_id]
        if len(inbound["settings"]["clients"]) == before:
            return False
        self.frontend_repo.write_config(config)
        meta = self.meta_repo.read()
        meta.get("clients", {}).pop(client_id, None)
        self.meta_repo.write(meta)
        self.frontend_repo.restart_frontend()
        return True

    def get_topology_health(self) -> TopologyHealthResult:
        clients = self.list_clients()
        return TopologyHealthResult(
            frontend_service=self.frontend_repo.get_frontend_service_status(),
            relay_service=self.relay_repo.get_remote_service_status(),
            relay_reachable=self.relay_repo.is_port_reachable(),
            expected_egress_ip=self.expected_egress_ip,
            client_count=len(clients),
            online_count=sum(1 for item in clients if item.status == "online"),
        )

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
        from urllib.parse import urlencode, quote

        return f"vless://{client.id}@{host}:{frontend_config.port}?{urlencode(query)}#{quote(client.name)}"

    def _parse_activity(self) -> dict:
        result = {}
        if not self.frontend_repo.access_log_path.exists():
            return result
        line_re = re.compile(r'^(?P<ts>\d{4}/\d{2}/\d{2} \d{2}:\d{2}:\d{2}\.\d+) from (?P<ip>[^:]+):\d+ accepted .*? \[(?P<inbound>[^\]]+) ->')
        lines = self.frontend_repo.access_log_path.read_text(errors="ignore").splitlines()[-2000:]
        for line in lines:
            match = line_re.search(line)
            if not match or match.group("inbound") != "frontend-in":
                continue
            seen_at = datetime.strptime(match.group("ts"), "%Y/%m/%d %H:%M:%S.%f").replace(tzinfo=timezone.utc)
            ip = match.group("ip")
            previous = result.get(ip)
            if not previous or seen_at > previous["last_seen_dt"]:
                result[ip] = {
                    "last_seen_dt": seen_at,
                    "last_seen": seen_at.isoformat().replace("+00:00", "Z"),
                    "source_ip": ip,
                }
        return result
