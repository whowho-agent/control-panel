from fastapi import FastAPI, status
from fastapi.responses import JSONResponse

from app.api.deps import get_xray_frontend_service
from app.api.ui import router as ui_router
from app.api.xray_frontend import router as xray_frontend_router

app = FastAPI(title="Xray Control Plane", version="0.1.0")
app.include_router(ui_router)
app.include_router(xray_frontend_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/ready")
def ready() -> JSONResponse:
    service = get_xray_frontend_service()
    readiness = service.frontend_repo.get_frontend_readiness()
    body = {"status": "ready" if readiness.ready else "not-ready", "details": readiness.message}
    code = status.HTTP_200_OK if readiness.ready else status.HTTP_503_SERVICE_UNAVAILABLE
    return JSONResponse(status_code=code, content=body)
