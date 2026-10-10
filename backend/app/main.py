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

app = FastAPI(title="CrisisGrid", version="0.1.0")
app.include_router(experiments_router)
app.include_router(graph_router)
app.include_router(runner_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {"status": "ok"}
