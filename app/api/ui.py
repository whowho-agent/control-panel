import subprocess
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from fastapi.templating import Jinja2Templates
from pydantic import ValidationError

from app.api.deps import get_xray_frontend_service, require_basic_auth
from app.api.schemas import CreateClientInput, UpdateFrontendConfigInput, UpdateRelayConfigInput, UpdateSniffingInput
from app.domain.xray_frontend import ControlPlaneError, CreateFrontendClientCommand
from app.domain.xray_frontend_config import (
    UpdateFrontendConfigCommand,
    UpdateRelayConfigCommand,
    UpdateSniffingCommand,
)
from app.services.xray_frontend_service import XrayFrontendService

router = APIRouter(tags=["ui"])
templates = Jinja2Templates(directory="app/templates")


def _query_message(request: Request, key: str) -> str:
    return request.query_params.get(key, "").strip()


def _humanize_message(message: str) -> str:
    mapping = {
        "client_created": "Client created and frontend is ready.",
        "client_deleted": "Client deleted and frontend is ready.",
        "client_enabled": "Client enabled and frontend is ready.",
        "client_disabled": "Client disabled and frontend is ready.",
        "frontend_config_saved": "Frontend config applied successfully. Preflight passed, restart succeeded, readiness is green.",
        "relay_config_saved": "Relay config applied successfully. Preflight passed, restart succeeded, readiness is green.",
        "sniffing_config_saved": "Sniffing config applied successfully.",
        "frontend_config_valid": "Frontend candidate config passed preflight validation. No restart was performed.",
        "relay_config_valid": "Relay candidate config passed preflight validation. No restart was performed.",
        "client_not_found": "Client not found.",
    }
    return mapping.get(message, message)


def _redirect_with_message(path: str, *, success: str = "", error: str = "") -> RedirectResponse:
    query = urlencode({k: v for k, v in {"success": success, "error": error}.items() if v})
    url = f"{path}?{query}" if query else path
    return RedirectResponse(url=url, status_code=303)


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
            "egress_label": topology.active_relay_host or frontend.relay_host or "egress",
            "success_message": _humanize_message(_query_message(request, "success")),
            "error_message": _humanize_message(_query_message(request, "error")),
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
    return templates.TemplateResponse(
        request,
        "clients.html",
        {
            "rows": rows,
            "success_message": _humanize_message(_query_message(request, "success")),
            "error_message": _humanize_message(_query_message(request, "error")),
        },
    )


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
    try:
        payload = CreateClientInput(name=name, host=host)
        service.create_client(CreateFrontendClientCommand(name=payload.name, host=payload.host))
    except (ValidationError, ControlPlaneError) as exc:
        return _redirect_with_message("/clients", error=str(exc))
    return _redirect_with_message("/clients", success="client_created")


@router.post("/clients/{client_id}/delete")
def delete_client(
    client_id: str,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    try:
        deleted = service.delete_client(client_id)
    except ControlPlaneError as exc:
        return _redirect_with_message("/clients", error=str(exc))
    if not deleted:
        return _redirect_with_message("/clients", error="client_not_found")
    return _redirect_with_message("/clients", success="client_deleted")


@router.post("/clients/{client_id}/enable")
def enable_client(
    client_id: str,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    try:
        updated = service.set_client_enabled(client_id, True)
    except ControlPlaneError as exc:
        return _redirect_with_message("/clients", error=str(exc))
    if not updated:
        return _redirect_with_message("/clients", error="client_not_found")
    return _redirect_with_message("/clients", success="client_enabled")


@router.post("/clients/{client_id}/disable")
def disable_client(
    client_id: str,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    try:
        updated = service.set_client_enabled(client_id, False)
    except ControlPlaneError as exc:
        return _redirect_with_message("/clients", error=str(exc))
    if not updated:
        return _redirect_with_message("/clients", error="client_not_found")
    return _redirect_with_message("/clients", success="client_disabled")


@router.get("/config", response_class=HTMLResponse)
def config_page(
    request: Request,
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> HTMLResponse:
    frontend = service.get_frontend_config()
    relay = service.get_relay_config()
    topology = service.get_topology_health()
    sniffing = service.get_sniffing_config()
    return templates.TemplateResponse(
        request,
        "config.html",
        {
            "frontend": frontend,
            "relay": relay,
            "topology": topology,
            "sniffing": sniffing,
            "success_message": _humanize_message(_query_message(request, "success")),
            "error_message": _humanize_message(_query_message(request, "error")),
        },
    )


@router.post("/config/frontend/validate")
def validate_frontend_config(
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
    try:
        payload = UpdateFrontendConfigInput(
            port=frontend_port,
            server_name=frontend_sni,
            fingerprint=frontend_fp,
            target=frontend_target,
            spider_x=frontend_spider,
            short_ids=[item.strip() for item in frontend_shortids.split(",") if item.strip()],
            relay_host=relay_host,
            relay_port=relay_port,
        )
        result = service.validate_frontend_config(UpdateFrontendConfigCommand(**payload.model_dump()))
    except (ValidationError, ControlPlaneError) as exc:
        return _redirect_with_message("/config", error=str(exc))
    if not result.preflight_ok:
        return _redirect_with_message("/config", error=result.message)
    return _redirect_with_message("/config", success="frontend_config_valid")


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
    try:
        payload = UpdateFrontendConfigInput(
            port=frontend_port,
            server_name=frontend_sni,
            fingerprint=frontend_fp,
            target=frontend_target,
            spider_x=frontend_spider,
            short_ids=[item.strip() for item in frontend_shortids.split(",") if item.strip()],
            relay_host=relay_host,
            relay_port=relay_port,
        )
        service.update_frontend_config(UpdateFrontendConfigCommand(**payload.model_dump()))
    except (ValidationError, ControlPlaneError) as exc:
        return _redirect_with_message("/config", error=str(exc))
    return _redirect_with_message("/config", success="frontend_config_saved")


@router.post("/config/relay/validate")
def validate_relay_config(
    relay_public_host: str = Form(...),
    relay_listen_port: int = Form(...),
    relay_uuid: str = Form(...),
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    try:
        payload = UpdateRelayConfigInput(
            public_host=relay_public_host,
            listen_port=relay_listen_port,
            relay_uuid=relay_uuid,
        )
        result = service.validate_relay_config(UpdateRelayConfigCommand(**payload.model_dump()))
    except (ValidationError, ControlPlaneError) as exc:
        return _redirect_with_message("/config", error=str(exc))
    if not result.preflight_ok:
        return _redirect_with_message("/config", error=result.message)
    return _redirect_with_message("/config", success="relay_config_valid")


@router.post("/config/sniffing")
def update_sniffing_config(
    sniffing_enabled: str = Form(default=""),
    sniffing_http: str = Form(default=""),
    sniffing_tls: str = Form(default=""),
    sniffing_quic: str = Form(default=""),
    sniffing_fakedns: str = Form(default=""),
    sniffing_route_only: str = Form(default=""),
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    dest_override = [
        proto
        for proto, val in [("http", sniffing_http), ("tls", sniffing_tls), ("quic", sniffing_quic), ("fakedns", sniffing_fakedns)]
        if val
    ]
    try:
        payload = UpdateSniffingInput(
            enabled=bool(sniffing_enabled),
            dest_override=dest_override,
            route_only=bool(sniffing_route_only),
        )
        service.update_sniffing_config(UpdateSniffingCommand(**payload.model_dump()))
    except (ValidationError, ControlPlaneError) as exc:
        return _redirect_with_message("/config", error=str(exc))
    return _redirect_with_message("/config", success="sniffing_config_saved")


@router.post("/config/relay")
def update_relay_config(
    relay_public_host: str = Form(...),
    relay_listen_port: int = Form(...),
    relay_uuid: str = Form(...),
    _: str = Depends(require_basic_auth),
    service: XrayFrontendService = Depends(get_xray_frontend_service),
) -> RedirectResponse:
    try:
        payload = UpdateRelayConfigInput(
            public_host=relay_public_host,
            listen_port=relay_listen_port,
            relay_uuid=relay_uuid,
        )
        service.update_relay_config(UpdateRelayConfigCommand(**payload.model_dump()))
    except (ValidationError, ControlPlaneError) as exc:
        return _redirect_with_message("/config", error=str(exc))
    return _redirect_with_message("/config", success="relay_config_saved")
