from app.repos.client_meta_repo import ClientMetaRepo
from app.repos.relay_node_repo import RelayNodeRepo
from app.repos.xray_frontend_repo import XrayFrontendRepo
from app.services.xray_frontend_service import XrayFrontendService


class Settings:
    frontend_config_path = "/opt/xray-frontend/config.json"
    frontend_access_log_path = "/opt/xray-frontend/access.log"
    frontend_service_name = "xray-frontend"
    xray_binary_path = "/opt/xray-frontend/xray"
    meta_path = "/opt/xray-frontend/clients-meta.json"
    relay_host = "72.56.109.197"
    relay_port = 9443
    relay_service_name = "xray-relay"
    relay_ssh_key_path = "/root/.openclaw/workspace/keys/rabotyaga_ed25519"
    relay_ssh_user = "root"
    online_window_minutes = 5
    expected_egress_ip = "72.56.109.197"


def get_xray_frontend_service() -> XrayFrontendService:
    settings = Settings()
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
    )
