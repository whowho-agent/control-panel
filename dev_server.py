"""
Dev server with fake data — for local UI development only.
Usage: uv run python dev_server.py
Then open: http://127.0.0.1:8000  (login: admin / change-me)
"""

from datetime import datetime, timezone

import uvicorn

from app.api.deps import get_xray_frontend_service
from app.domain.activity_log import ActivityLogEntry
from app.domain.xray_frontend import (
    FrontendClient,
    FrontendConfigResult,
    RelayConfigResult,
    SniffingConfigResult,
    TopologyHealthResult,
)
from app.main import app


class FakeService:
    def get_topology_health(self) -> TopologyHealthResult:
        return TopologyHealthResult(
            frontend_service="active",
            relay_service="active",
            relay_reachable=True,
            expected_egress_ip="72.56.109.197",
            client_count=4,
            online_count=2,
            egress_probe_ok=True,
            observed_egress_ip="72.56.109.197",
            frontend_ready=True,
            frontend_readiness_status="ready",
            transport_mode="ipsec",
            transport_label="IPSec private relay",
            relay_public_host="relay.example.com",
            relay_private_host="10.10.0.2",
            active_relay_host="10.10.0.2",
            active_relay_port=9443,
            ipsec_expected=True,
            ipsec_active=True,
            ipsec_local_tunnel_ip="10.10.0.1",
            ipsec_remote_tunnel_ip="10.10.0.2",
        )

    def get_frontend_config(self) -> FrontendConfigResult:
        return FrontendConfigResult(
            port=9444,
            server_name="mitigator.ru",
            public_key="BK9z1LmZpZHq3mP2wXkTvNdRqOeY7sJfCaGhLxUoWnE=",
            private_key="hidden",
            fingerprint="firefox",
            short_ids=["a1b2c3d4", "e5f6g7h8"],
            spider_x="/",
            target="mitigator.ru:443",
            relay_host="10.10.0.2",
            relay_port=9443,
            relay_uuid="f47ac10b-58cc-4372-a567-0e02b2c3d479",
        )

    def get_relay_config(self) -> RelayConfigResult:
        return RelayConfigResult(
            host="relay.example.com",
            port=9443,
            uuid="f47ac10b-58cc-4372-a567-0e02b2c3d479",
        )

    def list_clients(self) -> list[FrontendClient]:
        return [
            FrontendClient(
                id="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                name="alice-phone",
                short_id="a1b2c3d4",
                last_seen="2026-03-25 14:32",
                source_ip="91.108.4.55",
                status="online",
                enabled=True,
            ),
            FrontendClient(
                id="b2c3d4e5-f6a7-8901-bcde-f12345678901",
                name="bob-laptop",
                short_id="b2c3d4e5",
                last_seen="2026-03-25 14:28",
                source_ip="185.76.10.3",
                status="online",
                enabled=True,
            ),
            FrontendClient(
                id="c3d4e5f6-a7b8-9012-cdef-123456789012",
                name="carol-tablet",
                short_id="c3d4e5f6",
                last_seen="2026-03-24 09:11",
                source_ip="",
                status="activity-unattributed",
                enabled=True,
            ),
            FrontendClient(
                id="d4e5f6a7-b8c9-0123-defa-234567890123",
                name="dave-old-device",
                short_id="d4e5f6a7",
                last_seen="2026-03-20 18:00",
                source_ip="",
                status="offline",
                enabled=False,
            ),
        ]

    def build_client_uri(self, host: str, client: FrontendClient, frontend_config: FrontendConfigResult) -> str:
        return (
            f"vless://{client.id}@{host}:{frontend_config.port}"
            f"?type=tcp&security=reality&sni={frontend_config.server_name}"
            f"&fp={frontend_config.fingerprint}&pbk={frontend_config.public_key}"
            f"&sid={client.short_id}&spx={frontend_config.spider_x}"
            f"#{client.name}"
        )

    def create_client(self, cmd):
        pass

    def delete_client(self, client_id: str) -> bool:
        return True

    def set_client_enabled(self, client_id: str, enabled: bool) -> bool:
        return True

    def validate_frontend_config(self, cmd):
        from app.domain.xray_frontend import FrontendApplyResult
        return FrontendApplyResult(preflight_ok=True, restarted=False, ready=True, status="ok", message="Validation passed.")

    def validate_relay_config(self, cmd):
        from app.domain.xray_frontend import FrontendApplyResult
        return FrontendApplyResult(preflight_ok=True, restarted=False, ready=True, status="ok", message="Validation passed.")

    def update_frontend_config(self, cmd):
        pass

    def update_relay_config(self, cmd):
        pass

    def get_sniffing_config(self) -> SniffingConfigResult:
        return SniffingConfigResult(enabled=True, dest_override=["http", "tls"], route_only=False)

    def update_sniffing_config(self, cmd) -> SniffingConfigResult:
        return SniffingConfigResult(enabled=cmd.enabled, dest_override=cmd.dest_override, route_only=cmd.route_only)

    def get_recent_activity(self, minutes: int, limit: int = 100) -> list[ActivityLogEntry]:
        now = datetime.now(timezone.utc)
        return [
            ActivityLogEntry(
                timestamp=now,
                time_str=now.strftime("%H:%M:%S"),
                source_ip="91.108.4.55",
                destination="t.me:443",
                email="alice-phone",
            ),
            ActivityLogEntry(
                timestamp=now,
                time_str=now.strftime("%H:%M:%S"),
                source_ip="185.76.10.3",
                destination="google.com:443",
                email="bob-laptop",
            ),
        ]


app.dependency_overrides[get_xray_frontend_service] = lambda: FakeService()

if __name__ == "__main__":
    uvicorn.run(app, host="127.0.0.1", port=8001, reload=False)
