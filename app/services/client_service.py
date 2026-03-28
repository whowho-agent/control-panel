from __future__ import annotations

import logging
import secrets
import uuid
from dataclasses import replace
from datetime import datetime, timedelta, timezone

from app.domain.activity_log import ActivityLogEntry, parse_activity_lines
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
        clients_meta = meta.get("clients", {})

        activity_by_email = {v["email"]: v for v in activity.values() if v.get("email")}
        active_ids: set[str] = set()

        for item in config.frontend_clients():
            client_id = item["id"]
            active_ids.add(client_id)
            client_meta = clients_meta.get(client_id, {})
            last_seen = client_meta.get("last_seen", "")
            source_ip = client_meta.get("source_ip", "")
            email = item.get("email", "")
            matched_activity = activity_by_email.get(email)

            if matched_activity:
                last_seen = matched_activity["last_seen"]
                source_ip = matched_activity["source_ip"]
                if client_meta.get("last_seen") != last_seen or client_meta.get("source_ip") != source_ip:
                    meta = _update_client_meta(meta, client_id, last_seen, source_ip)
                    clients_meta = meta.get("clients", {})
                    meta_changed = True

            clients.append(
                FrontendClient(
                    id=client_id,
                    name=client_meta.get("name") or email or client_id,
                    short_id=client_meta.get("short_id", ""),
                    email=email,
                    created_at=client_meta.get("created_at", ""),
                    last_seen=last_seen,
                    source_ip=source_ip,
                    status=compute_status(
                        last_seen=last_seen,
                        enabled=True,
                        has_any_activity=bool(activity),
                        window_minutes=self._online_window_minutes,
                    ),
                    enabled=True,
                )
            )

        # Disabled clients: in meta with enabled=False, not in active config
        for client_id, client_meta in clients_meta.items():
            if client_id in active_ids:
                continue
            if client_meta.get("enabled", True):
                continue
            xray_entry = client_meta.get("xray_entry", {})
            email = xray_entry.get("email", "")
            last_seen = client_meta.get("last_seen", "")
            clients.append(
                FrontendClient(
                    id=client_id,
                    name=client_meta.get("name") or email or client_id,
                    short_id=client_meta.get("short_id", ""),
                    email=email,
                    created_at=client_meta.get("created_at", ""),
                    last_seen=last_seen,
                    source_ip=client_meta.get("source_ip", ""),
                    status=compute_status(
                        last_seen=last_seen,
                        enabled=False,
                        has_any_activity=bool(activity),
                        window_minutes=self._online_window_minutes,
                    ),
                    enabled=False,
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
        uri = self.build_uri(host, client, replace(frontend, short_ids=reality["shortIds"]))
        return FrontendClientUriResult(client=client, uri=uri)

    def delete(self, client_id: str) -> bool:
        config = self._frontend_repo.read_config()
        meta = self._meta_repo.read()
        original = config.frontend_clients()
        remaining_config = [c for c in original if c["id"] != client_id]
        config_changed = len(remaining_config) < len(original)
        client_meta = meta.get("clients", {}).get(client_id)
        is_disabled = client_meta is not None and not client_meta.get("enabled", True)

        if not config_changed and not is_disabled:
            return False

        if config_changed:
            config.set_frontend_clients(remaining_config)
            apply_result = self._frontend_repo.apply_config(config)
            if not apply_result.ready:
                raise ControlPlaneError(
                    "client_delete_apply_failed",
                    f"Client delete aborted because frontend apply failed: {apply_result.message}",
                    status_code=409,
                )

        remaining_meta = {k: v for k, v in meta.get("clients", {}).items() if k != client_id}
        self._meta_repo.write({**meta, "clients": remaining_meta})
        return True

    def set_enabled(self, client_id: str, enabled: bool) -> FrontendClient | None:
        config = self._frontend_repo.read_config()
        meta = self._meta_repo.read()
        clients_meta = meta.get("clients", {})
        client_meta = clients_meta.get(client_id, {})
        in_config = next((c for c in config.frontend_clients() if c["id"] == client_id), None)
        is_disabled_in_meta = not client_meta.get("enabled", True) and "xray_entry" in client_meta

        # Client must exist either in config (enabled) or in meta as disabled
        if in_config is None and not is_disabled_in_meta:
            return None

        if enabled:
            # Restore xray entry to config (if currently disabled)
            xray_entry = client_meta.get("xray_entry")
            if xray_entry and in_config is None:
                config.set_frontend_clients([*config.frontend_clients(), xray_entry])
            # Strip xray_entry and mark enabled in meta
            updated_client = {k: v for k, v in client_meta.items() if k != "xray_entry"}
            updated_client["enabled"] = True
        else:
            # Remove from config, store original entry in meta
            xray_entry = in_config or client_meta.get("xray_entry", {"id": client_id})
            if in_config is not None:
                config.set_frontend_clients([c for c in config.frontend_clients() if c["id"] != client_id])
            updated_client = {**client_meta, "enabled": False, "xray_entry": xray_entry}

        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "client_toggle_apply_failed",
                f"Client state change aborted because frontend apply failed: {apply_result.message}",
                status_code=409,
            )

        updated_meta = {**meta, "clients": {**clients_meta, client_id: updated_client}}
        self._meta_repo.write(updated_meta)

        xray_entry = updated_client.get("xray_entry") or in_config or {}
        email = xray_entry.get("email", "") if not enabled else (in_config or {}).get("email", "")
        last_seen = updated_client.get("last_seen", "")
        return FrontendClient(
            id=client_id,
            name=updated_client.get("name") or email or client_id,
            short_id=updated_client.get("short_id", ""),
            email=email,
            created_at=updated_client.get("created_at", ""),
            last_seen=last_seen,
            source_ip=updated_client.get("source_ip", ""),
            status=compute_status(
                last_seen=last_seen,
                enabled=enabled,
                has_any_activity=bool(last_seen),
                window_minutes=self._online_window_minutes,
            ),
            enabled=enabled,
        )

    def get_recent_activity(self, minutes: int, limit: int = 100) -> list[ActivityLogEntry]:
        lines = self._frontend_repo.read_access_log_lines()
        since = datetime.now(timezone.utc) - timedelta(minutes=minutes)
        return parse_activity_lines(lines, since, limit=limit)

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
