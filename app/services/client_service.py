from __future__ import annotations

import logging
import secrets
import uuid
from datetime import datetime, timezone

from app.domain.client_status import compute_status
from app.domain.vless_uri import VlessUriBuilder
from app.domain.xray_frontend import (
    ControlPlaneError,
    CreateFrontendClientCommand,
    FrontendClient,
    FrontendClientUriResult,
    FrontendConfigResult,
)
from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo

logger = logging.getLogger(__name__)


class ClientService:
    def __init__(
        self,
        frontend_repo: XrayFrontendRepo,
        meta_repo: ClientMetaRepo,
        online_window_minutes: int,
    ) -> None:
        self._frontend_repo = frontend_repo
        self._meta_repo = meta_repo
        self._online_window_minutes = online_window_minutes

    def list(self) -> list[FrontendClient]:
        activity = self._frontend_repo.parse_activity()
        clients, meta, meta_changed = self._build_clients(activity)
        if meta_changed:
            self._meta_repo.write(meta)
        return clients

    def _build_clients(self, activity: dict) -> tuple[list[FrontendClient], dict, bool]:
        config = self._frontend_repo.read_config()
        meta = self._meta_repo.read()
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
                window_minutes=self._online_window_minutes,
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

    def create(self, command: CreateFrontendClientCommand) -> FrontendClientUriResult:
        name = command.name.strip()
        host = command.host.strip()
        if not name:
            raise ControlPlaneError("client_name_empty", "Client name must not be empty")
        if not host:
            raise ControlPlaneError("client_host_empty", "Client host must not be empty")

        config = self._frontend_repo.read_config()
        frontend = self._frontend_repo.get_frontend_config()
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
        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_create_apply_failed",
                f"Client was not created because frontend apply failed: {apply_result.message}",
                status_code=409,
            )

        meta = self._meta_repo.read()
        new_entry = {
            "name": name,
            "short_id": short_id,
            "created_at": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "last_seen": "",
            "source_ip": "",
        }
        self._meta_repo.write({**meta, "clients": {**meta.get("clients", {}), client_id: new_entry}})

        client = FrontendClient(id=client_id, name=name, short_id=short_id, email=name)
        frontend.short_ids = reality["shortIds"]
        uri = self.build_uri(host, client, frontend)
        return FrontendClientUriResult(client=client, uri=uri)

    def delete(self, client_id: str) -> bool:
        config = self._frontend_repo.read_config()
        before = len(config.frontend_clients())
        config.set_frontend_clients([item for item in config.frontend_clients() if item.get("id") != client_id])
        if len(config.frontend_clients()) == before:
            return False
        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_delete_apply_failed",
                f"Client delete aborted because frontend apply failed: {apply_result.message}",
                status_code=409,
            )
        meta = self._meta_repo.read()
        remaining = {k: v for k, v in meta.get("clients", {}).items() if k != client_id}
        self._meta_repo.write({**meta, "clients": remaining})
        return True

    def set_enabled(self, client_id: str, enabled: bool) -> bool:
        config = self._frontend_repo.read_config()
        target = next(
            (item for item in config.frontend_clients() if item.get("id") == client_id),
            None,
        )
        if target is None:
            return False
        target["enable"] = enabled
        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_toggle_apply_failed",
                f"Client state change aborted because frontend apply failed: {apply_result.message}",
                status_code=409,
            )
        return True

    def build_uri(self, host: str, client: FrontendClient, frontend_config: FrontendConfigResult) -> str:
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
