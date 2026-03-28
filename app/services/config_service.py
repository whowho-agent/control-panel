import logging

from app.domain.xray_config import XrayConfigAccessor
from app.domain.xray_frontend import (
    ControlPlaneError,
    FrontendApplyResult,
    FrontendConfigResult,
    RelayConfigResult,
    SniffingConfigResult,
)
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand, UpdateSniffingCommand
from app.repos.xray_frontend_repo import XrayFrontendRepo

logger = logging.getLogger(__name__)


class ConfigService:
    def __init__(self, frontend_repo: XrayFrontendRepo) -> None:
        self._frontend_repo = frontend_repo

    def get_frontend(self) -> FrontendConfigResult:
        return self._frontend_repo.get_frontend_config()

    def get_relay(self) -> RelayConfigResult:
        return self._frontend_repo.get_relay_config_from_frontend()

    def validate_frontend(self, command: UpdateFrontendConfigCommand) -> FrontendApplyResult:
        config = self._build_frontend_candidate(command)
        return self._frontend_repo.validate_config(config)

    def validate_relay(self, command: UpdateRelayConfigCommand) -> FrontendApplyResult:
        config = self._build_relay_candidate(command)
        return self._frontend_repo.validate_config(config)

    def update_frontend(self, command: UpdateFrontendConfigCommand) -> FrontendConfigResult:
        config = self._build_frontend_candidate(command)
        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "frontend_apply_failed",
                f"Frontend config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self._frontend_repo.get_frontend_config()

    def update_relay(self, command: UpdateRelayConfigCommand) -> RelayConfigResult:
        config = self._build_relay_candidate(command)
        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "relay_apply_failed",
                f"Relay config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self._frontend_repo.get_relay_config_from_frontend()

    def get_sniffing(self) -> SniffingConfigResult:
        config = self._frontend_repo.read_config()
        raw = config.get_sniffing()
        return SniffingConfigResult(
            enabled=raw["enabled"],
            dest_override=list(raw.get("destOverride", [])),
            route_only=raw.get("routeOnly", False),
        )

    def update_sniffing(self, command: UpdateSniffingCommand) -> SniffingConfigResult:
        config = self._frontend_repo.read_config()
        config.set_sniffing(command.enabled, command.dest_override, command.route_only)
        apply_result = self._frontend_repo.apply_config(config)
        if not apply_result.ready:
            raise ControlPlaneError(
                "sniffing_apply_failed",
                f"Sniffing config was not applied: {apply_result.message}",
                status_code=409,
            )
        return self.get_sniffing()

    def _build_frontend_candidate(self, command: UpdateFrontendConfigCommand) -> XrayConfigAccessor:
        config = XrayConfigAccessor(self._frontend_repo.read_config().to_dict())
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

    def _build_relay_candidate(self, command: UpdateRelayConfigCommand) -> XrayConfigAccessor:
        config = XrayConfigAccessor(self._frontend_repo.read_config().to_dict())
        vnext = config.relay_outbound()["settings"]["vnext"][0]
        vnext["address"] = command.public_host
        vnext["port"] = command.listen_port
        vnext["users"][0]["id"] = command.relay_uuid
        return config
