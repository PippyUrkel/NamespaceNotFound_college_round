"""FastAPI endpoints for CrisisGrid Experiment Runner.

Exposes:
- Feasibility assessment
- Execution submission
- Status and manifest retrieval
- Cancellation
- Real-time progress monitoring
- Per-seed results inspection
- Resumption with retries or added seeds
- Evidence extraction for audit and claim verification
"""
from __future__ import annotations

import threading
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from .models import (
    EnvironmentBuildProgress,
    EnvironmentPreview,
    ExecutionManifest,
    FeasibilityReport,
    ResumeExecutionRequest,
    SubmitExecutionRequest,
)
from .service import RunnerService
from .environment_manager import EnvironmentManager

router = APIRouter(prefix="/experiments", tags=["runner"])
service = RunnerService()


@router.get("/{experiment_id}/environment-preview", response_model=EnvironmentPreview)
def get_experiment_environment_preview(
    experiment_id: str,
    version_id: str | None = Query(default=None),
    docker_image: str = Query(default="crisisgrid-ml-base:latest"),
    extra_packages: list[str] = Query(default=[]),
) -> EnvironmentPreview:
    """Preview Python imports across DAG nodes and verify library availability in the Docker image."""
    try:
        return service.get_environment_preview(
            experiment_id=experiment_id,
            graph_version_id=version_id,
            docker_image=docker_image,
            extra_packages=extra_packages,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Environment preview failed: {exc}") from exc


@router.get("/{experiment_id}/environment-build-progress", response_model=EnvironmentBuildProgress)
def get_experiment_environment_build_progress(experiment_id: str) -> EnvironmentBuildProgress:
    """Get the current or latest container environment library installation progress."""
    return service.get_environment_build_progress(experiment_id)


@router.post("/{experiment_id}/prepare-environment")
def prepare_experiment_environment(
    experiment_id: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """Pre-install required packages into a Docker image before execution."""
    packages = payload.get("packages", [])
    base_image = payload.get("base_image", "crisisgrid-ml-base:latest")
    async_build = payload.get("async_build", False)

    if async_build:
        EnvironmentManager._record_progress(
            experiment_id=experiment_id,
            status="building",
            docker_image=base_image,
            packages=packages,
            current_step=f"Queueing build for {len(packages)} packages...",
            percent=5,
            logs=[f"Build request queued for packages: {', '.join(packages)}"],
        )

        def run_build():
            try:
                service.prepare_environment(
                    experiment_id=experiment_id,
                    packages=packages,
                    base_image=base_image,
                )
            except Exception as e:
                print(f"[PrepareEnv Background Error] {e}", flush=True)

        thread = threading.Thread(target=run_build, daemon=True)
        thread.start()
        return {
            "status": "building",
            "experiment_id": experiment_id,
            "packages": packages,
            "message": "Environment build initiated in background",
        }

    try:
        return service.prepare_environment(
            experiment_id=experiment_id,
            packages=packages,
            base_image=base_image,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Environment preparation failed: {exc}") from exc


@router.get("/{experiment_id}/feasibility", response_model=FeasibilityReport)
def check_experiment_feasibility(
    experiment_id: str,
    version_id: str | None = Query(default=None),
    docker_image: str = Query(default="python:3.11-slim"),
) -> FeasibilityReport:
    """Assess whether host hardware, dependencies, and datasets can run the experiment."""
    try:
        return service.check_feasibility(
            experiment_id=experiment_id,
            graph_version_id=version_id,
            docker_image=docker_image,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Feasibility assessment failed: {exc}") from exc


@router.post("/{experiment_id}/executions", response_model=ExecutionManifest)
def submit_experiment_execution(
    experiment_id: str,
    request: SubmitExecutionRequest,
) -> ExecutionManifest:
    """Submit an experiment DAG for multi-seed containerized execution."""
    try:
        manifest = service.submit_execution(experiment_id, request)
        return manifest
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Execution failed: {exc}") from exc


@router.get("/{experiment_id}/executions")
def list_experiment_executions(experiment_id: str) -> list[dict[str, Any]]:
    """List all execution runs recorded for an experiment."""
    return service.list_executions(experiment_id)


@router.get("/{experiment_id}/executions/latest", response_model=ExecutionManifest)
def get_latest_experiment_execution(experiment_id: str) -> ExecutionManifest:
    """Get the latest execution manifest for an experiment."""
    manifest = service.get_latest_execution(experiment_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail="No executions found for this experiment")
    return manifest


@router.get("/{experiment_id}/executions/{execution_id}", response_model=ExecutionManifest)
def get_experiment_execution(experiment_id: str, execution_id: str) -> ExecutionManifest:
    """Get detailed execution manifest and per-seed results by ID."""
    manifest = service.get_execution_status(experiment_id, execution_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return manifest


@router.post("/{experiment_id}/executions/{execution_id}/cancel")
def cancel_experiment_execution(experiment_id: str, execution_id: str) -> dict[str, Any]:
    """Cancel a running experiment execution."""
    cancelled = service.cancel_execution(execution_id)
    if not cancelled:
        manifest = service.get_execution_status(experiment_id, execution_id)
        if manifest is None:
            raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
        return {"status": manifest.status.value, "cancelled": False, "detail": "Execution not actively running"}
    return {"status": "cancelling", "cancelled": True, "detail": "Cancellation signal sent"}


@router.get("/{experiment_id}/executions/{execution_id}/progress")
def get_execution_progress(experiment_id: str, execution_id: str) -> list[dict[str, Any]]:
    """Get structured progress events for an execution."""
    manifest = service.get_execution_status(experiment_id, execution_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return service.get_progress(execution_id)


@router.get("/{experiment_id}/executions/{execution_id}/seeds")
def get_per_seed_results(
    experiment_id: str,
    execution_id: str,
    seed: int | None = Query(default=None),
) -> list[dict[str, Any]]:
    """Inspect individual seed execution status, logs, runtime, and metrics."""
    manifest = service.get_execution_status(experiment_id, execution_id)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return service.get_seed_results(experiment_id, execution_id, seed=seed)


@router.post("/{experiment_id}/executions/{execution_id}/resume", response_model=ExecutionManifest)
def resume_experiment_execution(
    experiment_id: str,
    execution_id: str,
    request: ResumeExecutionRequest,
) -> ExecutionManifest:
    """Resume partially completed execution by retrying failed seeds or adding new seeds."""
    manifest = service.resume_execution(experiment_id, execution_id, request)
    if manifest is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return manifest


@router.get("/{experiment_id}/executions/{execution_id}/evidence")
def get_execution_audit_evidence(experiment_id: str, execution_id: str) -> dict[str, Any]:
    """Extract provenance and run evidence formatted for the audit and claim-verification modules.

    Keeps execution status strictly separate from scientific claims.
    """
    evidence = service.get_run_evidence(experiment_id, execution_id)
    if evidence is None:
        raise HTTPException(status_code=404, detail=f"Execution '{execution_id}' not found")
    return evidence
