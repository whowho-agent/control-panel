from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from app.api.deps import get_xray_frontend_service
from app.domain.xray_frontend import CreateFrontendClientCommand
from app.services.xray_frontend_service import XrayFrontendService

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> HTMLResponse:
    topology = service.get_topology_health()
    frontend = service.get_frontend_config()
    clients = service.list_clients()
    return templates.TemplateResponse(
        request,
        "dashboard.html",
        {
            "topology": topology,
            "frontend": frontend,
            "clients": clients,
            "online_count": sum(1 for client in clients if client.status == "online"),
        },
    )


@router.get("/clients", response_class=HTMLResponse)
def clients_page(request: Request, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> HTMLResponse:
    frontend = service.get_frontend_config()
    clients = service.list_clients()
    host = request.url.hostname or "127.0.0.1"
    rows = []
    for client in clients:
        rows.append(
            {
                "client": client,
                "uri": service.build_client_uri(host, client, frontend),
            }
        )
    return templates.TemplateResponse(request, "clients.html", {"rows": rows})


@router.post("/clients")
def create_client(
    request: Request,
    name: str = Form(...),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    host = request.url.hostname or "127.0.0.1"
    service.create_client(CreateFrontendClientCommand(name=name, host=host))
    return RedirectResponse(url="/clients", status_code=303)


@router.post("/clients/{client_id}/delete")
def delete_client(client_id: str, service: XrayFrontendService = Depends(get_xray_frontend_service)) -> RedirectResponse:
    service.delete_client(client_id)
    return RedirectResponse(url="/clients", status_code=303)
