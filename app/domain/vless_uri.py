from dataclasses import dataclass
from urllib.parse import quote, urlencode

from app.domain.xray_frontend import FrontendClient, FrontendConfigResult


@dataclass(frozen=True)
class VlessUriBuilder:
    def build(
        self,
        client: FrontendClient,
        host: str,
        config: FrontendConfigResult,
    ) -> str:
        query = {
            "type": "tcp",
            "security": "reality",
            "pbk": config.public_key,
            "fp": config.fingerprint,
            "sni": config.server_name,
            "sid": client.short_id or (config.short_ids[0] if config.short_ids else ""),
            "spx": config.spider_x,
            "encryption": "none",
        }
        return (
            f"vless://{client.id}@{host}:{config.port}?"
            f"{urlencode(query)}#{quote(client.name)}"
        )
