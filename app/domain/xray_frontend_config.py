from dataclasses import dataclass


@dataclass(slots=True)
class UpdateFrontendConfigCommand:
    port: int
    server_name: str
    fingerprint: str
    target: str
    spider_x: str
    short_ids: list[str]
    relay_host: str
    relay_port: int


@dataclass(slots=True)
class UpdateRelayConfigCommand:
    public_host: str
    listen_port: int
    relay_uuid: str
