from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from .service import ExperimentNotFound, ReportService

router = APIRouter(prefix="/experiments", tags=["report"])
service = ReportService()


@router.post("/{experiment_id}/report")
def generate_report(experiment_id: str) -> dict[str, Any]:
    try:
        return service.generate(experiment_id)
    except ExperimentNotFound as exc:
        raise HTTPException(status_code=404, detail="Experiment not found") from exc


@router.get("/{experiment_id}/report")
def get_report(experiment_id: str) -> dict[str, Any]:
    report = service.get(experiment_id)
    if report is None:
        raise HTTPException(status_code=404, detail="No report has been generated for this experiment")
    return report


@router.get("/{experiment_id}/report.md", response_class=PlainTextResponse)
def get_report_markdown(experiment_id: str) -> PlainTextResponse:
    markdown = service.get_markdown(experiment_id)
    if markdown is None:
        raise HTTPException(status_code=404, detail="No report has been generated for this experiment")
    return PlainTextResponse(markdown, media_type="text/markdown; charset=utf-8")


__all__ = ["router"]
