from __future__ import annotations

from fastapi import FastAPI

try:
    from backend.app.injestor.routes import router as experiments_router
    from backend.app.graph.routes import router as graph_router
    from backend.app.runner.routes import router as runner_router
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.routes import router as experiments_router
    from app.graph.routes import router as graph_router
    from app.runner.routes import router as runner_router

from fastapi.middleware.cors import CORSMiddleware

try:
    from backend.app.audit.routes import router as audit_router
except ModuleNotFoundError:  # pragma: no cover
    from app.audit.routes import router as audit_router

try:
    from backend.app.report.routes import router as report_router
except ModuleNotFoundError:  # pragma: no cover
    from app.report.routes import router as report_router

app = FastAPI(title="CrisisGrid", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(experiments_router)
app.include_router(graph_router)
app.include_router(runner_router)
app.include_router(audit_router)
app.include_router(report_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
