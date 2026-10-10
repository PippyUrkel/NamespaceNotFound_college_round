from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, Body, HTTPException

from .service import AuditService, ExecutionNotFound, ExperimentNotFound

router = APIRouter(prefix="/experiments", tags=["audit"])
service = AuditService()


@router.post("/{experiment_id}/audit/static")
def run_static_audit(experiment_id: str, background_tasks: BackgroundTasks, include_llm: bool = True) -> dict[str, Any]:
    try:
        result = service.run_static(experiment_id)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc

    if include_llm:
        background_tasks.add_task(service.run_llm, experiment_id)
        result = {**result, "llm_check": "started"}
    return result


@router.post("/{experiment_id}/audit/run")
def run_run_phase_audit(
    experiment_id: str,
    run_summaries: list[dict[str, Any]] | None = Body(default=None),
    execution_id: str | None = None,
) -> dict[str, Any]:
    """Compare reproduced results with the paper's claims.

    Without a body, results are read from the runner's execution (`execution_id`, or the latest one).
    """
    try:
        return service.run_run_phase(experiment_id, run_summaries, execution_id=execution_id)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc
    except ExecutionNotFound as exc:
        raise HTTPException(status_code=404, detail="No execution found for this experiment; run it first") from exc


@router.get("/{experiment_id}/audit")
def get_audit(experiment_id: str) -> dict[str, Any]:
    result = service.get_audit(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No audit has been run for this experiment")
    return result


__all__ = ["router"]
