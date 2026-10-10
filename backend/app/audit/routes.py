from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException

from .service import AuditService, ExperimentNotFound

router = APIRouter(prefix="/experiments", tags=["audit"])
service = AuditService()


@router.post("/{experiment_id}/audit/static")
def run_static_audit(experiment_id: str, background_tasks: BackgroundTasks, include_llm: bool = False) -> dict[str, Any]:
    try:
        result = service.run_static(experiment_id)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc

    if include_llm:
        background_tasks.add_task(service.run_llm, experiment_id)
        result = {**result, "llm_check": "started"}
    return result


@router.post("/{experiment_id}/audit/run")
def run_run_phase_audit(experiment_id: str, run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
    try:
        return service.run_run_phase(experiment_id, run_summaries)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@router.get("/{experiment_id}/audit")
def get_audit(experiment_id: str) -> dict[str, Any]:
    result = service.get_audit(experiment_id)
    if result is None:
        raise HTTPException(status_code=404, detail="No audit has been run for this experiment")
    return result


__all__ = ["router"]
