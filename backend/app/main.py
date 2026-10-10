from __future__ import annotations

from fastapi import FastAPI

try:
    from backend.app.injestor.routes import router as experiments_router
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.routes import router as experiments_router

try:
    from backend.app.audit.routes import router as audit_router
except ModuleNotFoundError:  # pragma: no cover
    from app.audit.routes import router as audit_router

app = FastAPI(title="CrisisGrid", version="0.1.0")
app.include_router(experiments_router)
app.include_router(audit_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
