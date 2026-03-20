from fastapi import FastAPI

from app.api.ui import router as ui_router
from app.api.xray_frontend import router as xray_frontend_router

app = FastAPI(title="Xray Control Plane", version="0.1.0")
app.include_router(ui_router)
app.include_router(xray_frontend_router)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}
