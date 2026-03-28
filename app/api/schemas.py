import re
from uuid import UUID

from pydantic import BaseModel, Field, field_validator

_SHORT_ID_RE = re.compile(r"^[0-9a-f]{1,16}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9.-]+$")
_TARGET_RE = re.compile(r"^[A-Za-z0-9.-]+:\d{1,5}$")


class CreateClientInput(BaseModel):
    name: str = Field(min_length=1, max_length=128)
    host: str = Field(min_length=1, max_length=255)

    @field_validator("name", "host")
    @classmethod
    def validate_trimmed_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if not _HOST_RE.fullmatch(value):
            raise ValueError("must be a valid hostname or IPv4 address")
        return value


class ClientOutput(BaseModel):
    id: str
    name: str
    short_id: str
    email: str = ""
    created_at: str = ""
    last_seen: str = ""
    source_ip: str = ""
    status: str
    enabled: bool = True


class CreateClientOutput(BaseModel):
    client: ClientOutput
    uri: str


class ApplyConfigOutput(BaseModel):
    preflight_ok: bool
    restarted: bool
    ready: bool
    status: str
    message: str = ""
    rollback_performed: bool = False


class TopologyHealthOutput(BaseModel):
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


class FrontendConfigOutput(BaseModel):
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


class RelayConfigOutput(BaseModel):
    host: str
    port: int
    uuid: str


class UpdateFrontendConfigInput(BaseModel):
    port: int = Field(ge=1, le=65535)
    server_name: str = Field(min_length=1, max_length=255)
    fingerprint: str = Field(min_length=1, max_length=64)
    target: str = Field(min_length=1, max_length=255)
    spider_x: str = Field(min_length=1, max_length=255)
    short_ids: list[str] = Field(min_length=1)
    relay_host: str = Field(min_length=1, max_length=255)
    relay_port: int = Field(ge=1, le=65535)

    @field_validator("server_name", "fingerprint", "target", "spider_x", "relay_host")
    @classmethod
    def validate_non_empty_trimmed_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("server_name", "relay_host")
    @classmethod
    def validate_host(cls, value: str) -> str:
        if not _HOST_RE.fullmatch(value):
            raise ValueError("must be a valid hostname or IPv4 address")
        return value

    @field_validator("target")
    @classmethod
    def validate_target(cls, value: str) -> str:
        if not _TARGET_RE.fullmatch(value):
            raise ValueError("must be in host:port format")
        host, port = value.rsplit(":", 1)
        if not _HOST_RE.fullmatch(host) or not (1 <= int(port) <= 65535):
            raise ValueError("must be in host:port format")
        return value

    @field_validator("short_ids")
    @classmethod
    def validate_short_ids(cls, value: list[str]) -> list[str]:
        normalized = []
        seen = set()
        for item in value:
            current = item.strip().lower()
            if not current:
                continue
            if not _SHORT_ID_RE.fullmatch(current):
                raise ValueError("short_ids must contain 1-16 lowercase hex chars")
            if current in seen:
                raise ValueError("short_ids must be unique")
            seen.add(current)
            normalized.append(current)
        if not normalized:
            raise ValueError("short_ids must not be empty")
        return normalized


_SNIFFING_ALLOWED = {"http", "tls", "quic", "fakedns"}


class SniffingConfigOutput(BaseModel):
    enabled: bool
    dest_override: list[str]
    route_only: bool


class UpdateSniffingInput(BaseModel):
    enabled: bool
    dest_override: list[str]
    route_only: bool = False

    @field_validator("dest_override")
    @classmethod
    def validate_dest_override(cls, value: list[str]) -> list[str]:
        seen: set[str] = set()
        result = []
        for item in value:
            if item not in _SNIFFING_ALLOWED:
                raise ValueError(f"invalid dest_override value '{item}'; allowed: {sorted(_SNIFFING_ALLOWED)}")
            if item not in seen:
                seen.add(item)
                result.append(item)
        return result


class UpdateRelayConfigInput(BaseModel):
    public_host: str = Field(min_length=1, max_length=255)
    listen_port: int = Field(ge=1, le=65535)
    relay_uuid: str = Field(min_length=1, max_length=64)

    @field_validator("public_host", "relay_uuid")
    @classmethod
    def validate_non_empty_trimmed_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be empty")
        return value

    @field_validator("public_host")
    @classmethod
    def validate_public_host(cls, value: str) -> str:
        if not _HOST_RE.fullmatch(value):
            raise ValueError("must be a valid hostname or IPv4 address")
        return value

    @field_validator("relay_uuid")
    @classmethod
    def validate_uuid(cls, value: str) -> str:
        UUID(value)
        return value
