FRONTEND_INBOUND_TAG = "frontend-in"
RELAY_OUTBOUND_TAG = "to-relay"


class XrayConfigAccessor:
    """Typed accessor for the Xray JSON config dict.

    Encapsulates all tag-based navigation so callers never hard-code
    ``"frontend-in"`` or ``"to-relay"`` outside this module.
    """

    def __init__(self, raw: dict) -> None:
        self._raw = raw

    def frontend_inbound(self) -> dict:
        try:
            return next(item for item in self._raw["inbounds"] if item.get("tag") == FRONTEND_INBOUND_TAG)
        except StopIteration:
            raise KeyError(f"No inbound with tag '{FRONTEND_INBOUND_TAG}' found in config")

    def relay_outbound(self) -> dict:
        try:
            return next(item for item in self._raw["outbounds"] if item.get("tag") == RELAY_OUTBOUND_TAG)
        except StopIteration:
            raise KeyError(f"No outbound with tag '{RELAY_OUTBOUND_TAG}' found in config")

    def frontend_clients(self) -> list[dict]:
        return self.frontend_inbound()["settings"].get("clients", [])

    def set_frontend_clients(self, clients: list[dict]) -> None:
        self.frontend_inbound()["settings"]["clients"] = clients

    def get_sniffing(self) -> dict:
        return self.frontend_inbound().get(
            "sniffing",
            {"enabled": False, "destOverride": [], "routeOnly": False},
        )

    def set_sniffing(self, enabled: bool, dest_override: list[str], route_only: bool) -> None:
        self.frontend_inbound()["sniffing"] = {
            "enabled": enabled,
            "destOverride": dest_override,
            "routeOnly": route_only,
        }

    def to_dict(self) -> dict:
        return self._raw
