from pydantic import BaseModel


class CreateClientInput(BaseModel):
    name: str
    host: str


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


class TopologyHealthOutput(BaseModel):
    frontend_service: str
    relay_service: str
    relay_reachable: bool
    expected_egress_ip: str
    client_count: int
    online_count: int


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
    port: int
    server_name: str
    fingerprint: str
    target: str
    spider_x: str
    short_ids: list[str]
    relay_host: str
    relay_port: int


class UpdateRelayConfigInput(BaseModel):
    public_host: str
    listen_port: int
    relay_uuid: str
