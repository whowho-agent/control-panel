import subprocess

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates

from app.api.deps import get_xray_frontend_service, require_basic_auth
from app.domain.xray_frontend import CreateFrontendClientCommand
from app.domain.xray_frontend_config import (
    UpdateFrontendConfigCommand,
    UpdateRelayConfigCommand,
)
from app.services.xray_frontend_service import XrayFrontendService

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(
    request: Request,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> HTMLResponse:
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
            "gateway_host": request.url.hostname or "localhost",
            "gateway_label": request.url.hostname or "gateway",
            "egress_label": frontend.relay_host or "egress",
        },
    )


@router.get("/clients", response_class=HTMLResponse)
def clients_page(
    request: Request,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> HTMLResponse:
    frontend = service.get_frontend_config()
    clients = service.list_clients()
    host = request.url.hostname or "127.0.0.1"
    rows = []
    for client in clients:
        rows.append({"client": client, "uri": service.build_client_uri(host, client, frontend)})
    return templates.TemplateResponse(request, "clients.html", {"rows": rows})


@router.get("/clients/{client_id}/qr")
def client_qr(
    client_id: str,
    request: Request,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> Response:
    host = request.url.hostname or "127.0.0.1"
    frontend = service.get_frontend_config()
    client = next((item for item in service.list_clients() if item.id == client_id), None)
    if client is None:
        return Response(status_code=404)
    uri = service.build_client_uri(host, client, frontend)
    process = subprocess.run(["qrencode", "-o", "-", "-s", "8", "-m", "2", uri], capture_output=True)
    if process.returncode != 0:
        return Response(status_code=500)
    return Response(content=process.stdout, media_type="image/png")


@router.post("/clients")
def create_client(
    request: Request,
    name: str = Form(...),
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    host = request.url.hostname or "127.0.0.1"
    service.create_client(CreateFrontendClientCommand(name=name, host=host))
    return RedirectResponse(url="/clients", status_code=303)


@router.post("/clients/{client_id}/delete")
def delete_client(
    client_id: str,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    service.delete_client(client_id)
    return RedirectResponse(url="/clients", status_code=303)


@router.post("/clients/{client_id}/enable")
def enable_client(
    client_id: str,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    service.set_client_enabled(client_id, True)
    return RedirectResponse(url="/clients", status_code=303)


@router.post("/clients/{client_id}/disable")
def disable_client(
    client_id: str,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    service.set_client_enabled(client_id, False)
    return RedirectResponse(url="/clients", status_code=303)


@router.get("/config", response_class=HTMLResponse)
def config_page(
    request: Request,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> HTMLResponse:
    frontend = service.get_frontend_config()
    relay = service.get_relay_config()
    return templates.TemplateResponse(request, "config.html", {"frontend": frontend, "relay": relay})


@router.post("/config/frontend")
def update_frontend_config(
    frontend_port: int = Form(...),
    frontend_sni: str = Form(...),
    frontend_fp: str = Form(...),
    frontend_target: str = Form(...),
    frontend_spider: str = Form(...),
    frontend_shortids: str = Form(...),
    relay_host: str = Form(...),
    relay_port: int = Form(...),
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    service.update_frontend_config(
        UpdateFrontendConfigCommand(
            port=frontend_port,
            server_name=frontend_sni,
            fingerprint=frontend_fp,
            target=frontend_target,
            spider_x=frontend_spider,
            short_ids=[item.strip() for item in frontend_shortids.split(',') if item.strip()],
            relay_host=relay_host,
            relay_port=relay_port,
        )
    )
    return RedirectResponse(url="/config", status_code=303)


@router.post("/config/relay")
def update_relay_config(
    relay_public_host: str = Form(...),
    relay_listen_port: int = Form(...),
    relay_uuid: str = Form(...),
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    service.update_relay_config(
        UpdateRelayConfigCommand(
            public_host=relay_public_host,
            listen_port=relay_listen_port,
            relay_uuid=relay_uuid,
        )
    )
    return RedirectResponse(url="/config", status_code=303)
