from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .models import GraphDiff, GraphVersion, TuneParameterRequest
from .service import GraphService

router = APIRouter(prefix="/experiments", tags=["graph"])
service = GraphService()


@router.get("/{experiment_id}/graph", response_model=GraphVersion)
def get_experiment_graph(experiment_id: str) -> GraphVersion:
    graph = service.get_or_create_graph(experiment_id)
    if graph is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return graph


@router.post("/{experiment_id}/graph/generate", response_model=GraphVersion)
def generate_experiment_graph(experiment_id: str, force: bool = Query(default=False)) -> GraphVersion:
    graph = service.generate_graph(experiment_id, force=force)
    if graph is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return graph


@router.post("/{experiment_id}/graph/tune", response_model=GraphVersion)
def tune_experiment_parameters(experiment_id: str, request: TuneParameterRequest) -> GraphVersion:
    try:
        new_version = service.tune_graph(experiment_id, request)
        return new_version
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Parameter tuning failed: {exc}") from exc


@router.get("/{experiment_id}/graph/versions")
def list_experiment_graph_versions(experiment_id: str) -> list[dict[str, Any]]:
    versions = service.get_all_versions(experiment_id)
    if not versions:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return [
        {
            "version_id": v.version_id,
            "parent_version": v.parent_version,
            "created_at": v.created_at,
            "change_description": v.change_description,
            "graph_hash": v.graph_hash,
            "node_count": len(v.nodes),
            "parameters_summary": v.parameters_summary,
        }
        for v in versions
    ]


@router.get("/{experiment_id}/graph/versions/{version_id}", response_model=GraphVersion)
def get_experiment_graph_version(experiment_id: str, version_id: str) -> GraphVersion:
    version = service.get_version(experiment_id, version_id)
    if version is None:
        raise HTTPException(status_code=404, detail=f"Graph version '{version_id}' not found")
    return version


@router.get("/{experiment_id}/graph/diff", response_model=GraphDiff)
def get_experiment_graph_diff(
    experiment_id: str,
    from_version: str | None = Query(default=None),
    to_version: str | None = Query(default=None),
) -> GraphDiff:
    try:
        return service.diff_versions(experiment_id, from_version_id=from_version, to_version_id=to_version)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail=f"Diff calculation failed: {exc}") from exc
