import os
import secrets
from functools import lru_cache

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo
from app.services.xray_frontend_service import XrayFrontendService


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
        self.xray_binary_path = os.getenv("XRAY_BINARY_PATH", "/opt/xray-frontend/xray")
        self.meta_path = os.getenv(
            "XRAY_CLIENT_META_PATH",
            "/opt/xray-frontend/clients-meta.json",
        )
        self.relay_host = os.getenv("XRAY_RELAY_HOST", "72.56.109.197")
        self.relay_port = int(os.getenv("XRAY_RELAY_PORT", "9443"))
        self.relay_service_name = os.getenv("XRAY_RELAY_SERVICE_NAME", "xray-relay")
        self.relay_ssh_key_path = os.getenv(
            "XRAY_RELAY_SSH_KEY_PATH",
            "/root/.openclaw/workspace/keys/rabotyaga_ed25519",
        )
        self.relay_ssh_user = os.getenv("XRAY_RELAY_SSH_USER", "root")
        self.online_window_minutes = int(os.getenv("XRAY_ONLINE_WINDOW_MINUTES", "5"))
        self.expected_egress_ip = os.getenv("XRAY_EXPECTED_EGRESS_IP", "72.56.109.197")
        self.admin_user = os.getenv("XRAY_ADMIN_USER", "admin")
        self.admin_password = os.getenv("XRAY_ADMIN_PASSWORD", "cfuQXkmySEy7Q0MYN8ruwCs-")
        self.topology_cache_ttl_seconds = int(os.getenv("XRAY_TOPOLOGY_CACHE_TTL_SECONDS", "10"))


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


def get_xray_frontend_service(settings: Settings = Depends(get_settings)) -> XrayFrontendService:
    frontend_repo = XrayFrontendRepo(
        config_path=settings.frontend_config_path,
        access_log_path=settings.frontend_access_log_path,
        service_name=settings.frontend_service_name,
        xray_binary_path=settings.xray_binary_path,
    )
    meta_repo = ClientMetaRepo(meta_path=settings.meta_path)
    relay_repo = RelayNodeRepo(
        host=settings.relay_host,
        port=settings.relay_port,
        service_name=settings.relay_service_name,
        ssh_key_path=settings.relay_ssh_key_path,
        ssh_user=settings.relay_ssh_user,
    )
    return XrayFrontendService(
        frontend_repo=frontend_repo,
        meta_repo=meta_repo,
        relay_repo=relay_repo,
        online_window_minutes=settings.online_window_minutes,
        expected_egress_ip=settings.expected_egress_ip,
        topology_cache_ttl_seconds=settings.topology_cache_ttl_seconds,
    )
