from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_xray_frontend_service, require_basic_auth
from app.api.schemas import (
    ClientOutput,
    CreateClientInput,
    CreateClientOutput,
    FrontendConfigOutput,
    RelayConfigOutput,
    TopologyHealthOutput,
    UpdateFrontendConfigInput,
    UpdateRelayConfigInput,
)
from app.domain.xray_frontend import CreateFrontendClientCommand
from app.domain.xray_frontend_config import UpdateFrontendConfigCommand, UpdateRelayConfigCommand
from app.services.xray_frontend_service import XrayFrontendService

router = APIRouter(prefix="/api/xray-frontend", tags=["xray-frontend"], dependencies=[Depends(require_basic_auth)])


@router.get("/clients", response_model=list[ClientOutput], summary="List frontend clients")
def list_clients(service: XrayFrontendService = Depends(get_xray_frontend_service)) -> list[ClientOutput]:
    return [ClientOutput(**client.__dict__) for client in service.list_clients()]


@router.post(
    "/clients",
    response_model=CreateClientOutput,
    status_code=status.HTTP_201_CREATED,
    summary="Create frontend client",
)
def create_client(payload: CreateClientInput, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> CreateClientOutput:
    result = service.create_client(CreateFrontendClientCommand(name=payload.name, host=payload.host))
    return CreateClientOutput(client=ClientOutput(**result.client.__dict__), uri=result.uri)


@router.delete("/clients/{client_id}", status_code=status.HTTP_204_NO_CONTENT, summary="Delete frontend client")
def delete_client(client_id: str, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> None:
    deleted = service.delete_client(client_id)
    if not deleted:
        raise HTTPException(status_code=404, detail="client_not_found")


@router.post("/clients/{client_id}/enable", response_model=ClientOutput, summary="Enable frontend client")
def enable_client(client_id: str, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> ClientOutput:
    updated = service.set_client_enabled(client_id, True)
    if not updated:
        raise HTTPException(status_code=404, detail="client_not_found")
    client = next(item for item in service.list_clients() if item.id == client_id)
    return ClientOutput(**client.__dict__)


@router.post("/clients/{client_id}/disable", response_model=ClientOutput, summary="Disable frontend client")
def disable_client(client_id: str, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> ClientOutput:
    updated = service.set_client_enabled(client_id, False)
    if not updated:
        raise HTTPException(status_code=404, detail="client_not_found")
    client = next(item for item in service.list_clients() if item.id == client_id)
    return ClientOutput(**client.__dict__)


@router.get("/topology-health", response_model=TopologyHealthOutput, summary="Get topology health")
def get_topology_health(service: XrayFrontendService = Depends(get_xray_frontend_service)) -> TopologyHealthOutput:
    return TopologyHealthOutput(**service.get_topology_health().__dict__)


@router.get("/config/frontend", response_model=FrontendConfigOutput, summary="Get frontend config")
def get_frontend_config(service: XrayFrontendService = Depends(get_xray_frontend_service)) -> FrontendConfigOutput:
    return FrontendConfigOutput(**service.get_frontend_config().__dict__)


@router.put("/config/frontend", response_model=FrontendConfigOutput, summary="Update frontend config")
def update_frontend_config(
    payload: UpdateFrontendConfigInput,
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> FrontendConfigOutput:
    result = service.update_frontend_config(UpdateFrontendConfigCommand(**payload.model_dump()))
    return FrontendConfigOutput(**result.__dict__)


@router.get("/config/relay", response_model=RelayConfigOutput, summary="Get relay config")
def get_relay_config(service: XrayFrontendService = Depends(get_xray_frontend_service)) -> RelayConfigOutput:
    return RelayConfigOutput(**service.get_relay_config().__dict__)


@router.put("/config/relay", response_model=RelayConfigOutput, summary="Update relay config")
def update_relay_config(
    payload: UpdateRelayConfigInput,
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RelayConfigOutput:
    result = service.update_relay_config(UpdateRelayConfigCommand(**payload.model_dump()))
    return RelayConfigOutput(**result.__dict__)
