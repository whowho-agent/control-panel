"""
relay-agent — lightweight HTTP sidecar on the egress node.

Exposes /health and /status. Polls systemctl + ipify every 60s and caches
the result so callers never block on subprocess or external HTTP.
"""

import logging
import subprocess
import threading
import time
import urllib.request

import uvicorn
from fastapi import FastAPI

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

SERVICE_NAME = "xray-relay"
PROBE_INTERVAL_SECONDS = 60
IPIFY_URL = "https://api.ipify.org"
AGENT_PORT = 9100

app = FastAPI(title="relay-agent", version="1.0.0")

_cache: dict = {"service": "unknown", "egress_ip": "", "updated_at": 0.0}
_lock = threading.Lock()


# ---------------------------------------------------------------------------
# Probe helpers
# ---------------------------------------------------------------------------


def _probe_service() -> str:
    try:
        result = subprocess.run(
            ["systemctl", "is-active", SERVICE_NAME],
            capture_output=True,
            text=True,
            timeout=5,
        )
        status = result.stdout.strip()
        return status if status else "unknown"
    except Exception as exc:
        logger.warning("probe_service failed: %s", exc)
        return "unknown"


def _probe_egress_ip() -> str:
    try:
        with urllib.request.urlopen(IPIFY_URL, timeout=5) as resp:
            return resp.read().decode().strip()
    except Exception as exc:
        logger.warning("probe_egress_ip failed: %s", exc)
        return ""


def _poll_loop() -> None:
    while True:
        service = _probe_service()
        egress_ip = _probe_egress_ip()
        with _lock:
            _cache["service"] = service
            _cache["egress_ip"] = egress_ip
            _cache["updated_at"] = time.time()
        logger.info("probe: service=%s egress_ip=%s", service, egress_ip)
        time.sleep(PROBE_INTERVAL_SECONDS)


# Start background thread immediately on import (works with uvicorn workers)
_thread = threading.Thread(target=_poll_loop, daemon=True)
_thread.start()


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------


@app.get("/health")
def health() -> dict:
    return {"ok": True}


@app.get("/status")
def status() -> dict:
    with _lock:
        return {
            "service": _cache["service"],
            "egress_ip": _cache["egress_ip"],
            "updated_at": _cache["updated_at"],
        }


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=AGENT_PORT)
