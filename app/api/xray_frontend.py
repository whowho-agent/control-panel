from fastapi import APIRouter, Depends, HTTPException, status

from app.api.deps import get_xray_frontend_service
from app.api.schemas import ClientOutput, CreateClientInput, CreateClientOutput, TopologyHealthOutput
from app.domain.xray_frontend import CreateFrontendClientCommand
from app.services.xray_frontend_service import XrayFrontendService

router = APIRouter(prefix="/api/xray-frontend", tags=["xray-frontend"])


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


@router.get("/topology-health", response_model=TopologyHealthOutput, summary="Get topology health")
def get_topology_health(service: XrayFrontendService = Depends(get_xray_frontend_service)) -> TopologyHealthOutput:
    return TopologyHealthOutput(**service.get_topology_health().__dict__)
