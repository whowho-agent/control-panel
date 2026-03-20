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
