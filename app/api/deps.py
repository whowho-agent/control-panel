import logging
import os
import secrets
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo
from app.services.xray_frontend_service import XrayFrontendService

logger = logging.getLogger(__name__)


def _int_env(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError:
        raise RuntimeError(
            f"Environment variable {name}={raw!r} is not a valid integer"
        ) from None


class Settings:
    def __init__(self) -> None:
        self.frontend_config_path = os.getenv(
            "XRAY_FRONTEND_CONFIG_PATH",
            "/opt/xray-frontend/config.json",
        )
        self.frontend_access_log_path = os.getenv(
            "XRAY_FRONTEND_ACCESS_LOG_PATH",
            "/opt/xray-frontend/access.log",
        )
        self.frontend_service_name = os.getenv(
            "XRAY_FRONTEND_SERVICE_NAME",
            "xray-frontend",
        )
        self.frontend_use_nsenter = os.getenv("XRAY_FRONTEND_USE_NSENTER", "0") == "1"
        self.xray_binary_path = os.getenv("XRAY_BINARY_PATH", "/opt/xray-frontend/xray")
        self.meta_path = os.getenv(
            "XRAY_CLIENT_META_PATH",
            "/opt/xray-frontend/clients-meta.json",
        )
        self.relay_host = os.getenv("XRAY_RELAY_HOST", "relay.example.com")
        self.relay_port = _int_env("XRAY_RELAY_PORT", 9443)
        self.relay_agent_url = os.getenv(
            "XRAY_RELAY_AGENT_URL",
            f"http://{self.relay_host}:9100",
        )
        self.online_window_minutes = _int_env("XRAY_ONLINE_WINDOW_MINUTES", 5)
        self.expected_egress_ip = os.getenv("XRAY_EXPECTED_EGRESS_IP", "203.0.113.10")
        self.admin_user = os.getenv("XRAY_ADMIN_USER", "admin")
        self.admin_password = os.getenv("XRAY_ADMIN_PASSWORD", "change-me")
        if self.admin_password == "change-me":
            logger.critical(
                "XRAY_ADMIN_PASSWORD is set to the default value 'change-me'. "
                "Set a strong password via the XRAY_ADMIN_PASSWORD environment variable before exposing this service."
            )
        self.topology_cache_ttl_seconds = _int_env("XRAY_TOPOLOGY_CACHE_TTL_SECONDS", 10)
        self.transport_mode = os.getenv("XRAY_TRANSPORT_MODE", "direct").strip().lower() or "direct"
        self.relay_public_host = os.getenv("XRAY_RELAY_PUBLIC_HOST", self.relay_host)
        self.relay_private_host = os.getenv("XRAY_RELAY_PRIVATE_HOST", "")
        self.ipsec_local_tunnel_ip = os.getenv("XRAY_IPSEC_LOCAL_TUNNEL_IP", "")
        self.ipsec_remote_tunnel_ip = os.getenv("XRAY_IPSEC_REMOTE_TUNNEL_IP", "")


security = HTTPBasic()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


def require_basic_auth(
    credentials: HTTPBasicCredentials = Depends(security),
    settings: Settings = Depends(get_settings),
) -> str:
    valid_user = secrets.compare_digest(credentials.username, settings.admin_user)
    valid_password = secrets.compare_digest(credentials.password, settings.admin_password)
    if not (valid_user and valid_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="unauthorized",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username


@lru_cache(maxsize=1)
def get_xray_frontend_service() -> XrayFrontendService:
    settings = get_settings()
    frontend_repo = XrayFrontendRepo(
        config_path=settings.frontend_config_path,
        access_log_path=settings.frontend_access_log_path,
        service_name=settings.frontend_service_name,
        xray_binary_path=settings.xray_binary_path,
        use_nsenter=settings.frontend_use_nsenter,
    )
    meta_repo = ClientMetaRepo(meta_path=settings.meta_path)
    relay_repo = RelayNodeRepo(
        host=settings.relay_host,
        port=settings.relay_port,
        agent_url=settings.relay_agent_url,
    )
    return XrayFrontendService(
        frontend_repo=frontend_repo,
        meta_repo=meta_repo,
        relay_repo=relay_repo,
        online_window_minutes=settings.online_window_minutes,
        expected_egress_ip=settings.expected_egress_ip,
        topology_cache_ttl_seconds=settings.topology_cache_ttl_seconds,
        transport_mode=settings.transport_mode,
        relay_public_host=settings.relay_public_host,
        relay_private_host=settings.relay_private_host,
        ipsec_local_tunnel_ip=settings.ipsec_local_tunnel_ip,
        ipsec_remote_tunnel_ip=settings.ipsec_remote_tunnel_ip,
    )
