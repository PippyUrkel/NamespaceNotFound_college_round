"""Runner service — main orchestrator for experiment execution.

Coordinates: feasibility checks, seed resolution, graph execution,
result collection, and manifest persistence. Exposes the high-level
API consumed by the routes module.
"""
from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

try:
    from backend.config import settings
    from backend.app.graph.models import DAGNode, GraphVersion
    from backend.app.graph.service import GraphService
except ModuleNotFoundError:  # pragma: no cover
    from config import settings
    from app.graph.models import DAGNode, GraphVersion
    from app.graph.service import GraphService

from .cache import ExecutionCache
from .docker_worker import DockerWorker
from .executor import GraphExecutor
from .feasibility import FeasibilityChecker
from .models import (
    EnvironmentBuildProgress,
    EnvironmentPreview,
    ExecutionConfig,
    ExecutionManifest,
    ExecutionStatus,
    FeasibilityReport,
    ProgressEvent,
    ResumeExecutionRequest,
    RunStatus,
    SubmitExecutionRequest,
)
from .environment_manager import EnvironmentManager
from .dataset_manager import DatasetManager
from .results_collector import ResultsCollector
from .seed_coordinator import SeedCoordinator


class RunnerService:
    """Top-level experiment execution service."""

    def __init__(
        self,
        artifacts_dir: str | Path | None = None,
        docker_worker: DockerWorker | None = None,
    ) -> None:
        self._artifacts_dir = Path(artifacts_dir) if artifacts_dir else Path(settings.artifacts_dir)
        self._graph_service = GraphService(artifacts_dir=self._artifacts_dir)
        self._results = ResultsCollector(self._artifacts_dir)
        self._docker_worker = docker_worker
        self._active_executors: dict[str, GraphExecutor] = {}
        self._progress_log: dict[str, list[ProgressEvent]] = {}

    # ------------------------------------------------------------------
    # Feasibility & Environment Preview
    # ------------------------------------------------------------------
    def check_feasibility(
        self,
        experiment_id: str,
        graph_version_id: str | None = None,
        docker_image: str = "python:3.11-slim",
        pip_packages: list[str] | None = None,
    ) -> FeasibilityReport:
        """Run a pre-execution feasibility assessment."""
        graph = self._resolve_graph(experiment_id, graph_version_id)
        return FeasibilityChecker.check(
            graph=graph,
            docker_image=docker_image,
            pip_packages=pip_packages or [],
        )

    def get_environment_preview(
        self,
        experiment_id: str,
        graph_version_id: str | None = None,
        docker_image: str | None = None,
        extra_packages: list[str] | None = None,
    ) -> EnvironmentPreview:
        """Inspect all imports and verify library availability in Docker image before execution."""
        graph = self._resolve_graph(experiment_id, graph_version_id)
        spec = self._graph_service._load_spec(experiment_id)
        target_image = docker_image or "crisisgrid-ml-base:latest"
        return EnvironmentManager.get_environment_preview(
            graph=graph,
            docker_image=target_image,
            spec=spec,
            explicit_packages=extra_packages,
        )

    def get_environment_build_progress(self, experiment_id: str) -> EnvironmentBuildProgress:
        """Get current or latest environment build progress."""
        return EnvironmentManager.get_build_progress(experiment_id)

    def prepare_environment(
        self,
        experiment_id: str,
        packages: list[str],
        base_image: str = "crisisgrid-ml-base:latest",
    ) -> dict[str, Any]:
        """Pre-install required packages into a Docker image before execution."""
        prepared_image = EnvironmentManager.prepare_image(
            packages=packages,
            base_image=base_image,
            experiment_id=experiment_id,
        )
        if self._docker_worker:
            self._docker_worker._docker_image = prepared_image
        return {
            "docker_image": prepared_image,
            "packages": packages,
            "status": "ready",
        }

    # ------------------------------------------------------------------
    # Submit execution
    # ------------------------------------------------------------------
    def submit_execution(
        self,
        experiment_id: str,
        request: SubmitExecutionRequest,
    ) -> ExecutionManifest:
        """Submit an experiment for execution.

        Steps:
        1. Resolve the graph version
        2. Optionally run feasibility check
        3. Resolve seeds (from request, provenance, or defaults)
        4. Execute the graph for each seed
        5. Aggregate and persist results
        """
        graph = self._resolve_graph(experiment_id, request.graph_version_id)
        execution_id = f"exec_{uuid.uuid4().hex[:12]}"

        # Build execution config
        config = ExecutionConfig(
            seeds=request.seeds or [],
            **{k: v for k, v in request.config_overrides.items()
               if k in ExecutionConfig.model_fields},
        )

        # Resolve seeds
        seeds = SeedCoordinator.resolve_seeds(
            explicit_seeds=config.seeds if config.seeds else None,
            condition_provenance=graph.condition_provenance,
        )
        config.seeds = seeds

        # Combine explicit pip packages from request and config overrides
        explicit_pkgs = list(config.pip_packages)
        if request.pip_packages:
            for p in request.pip_packages:
                if p not in explicit_pkgs:
                    explicit_pkgs.append(p)

        # Detect required dependencies from graph code and spec
        spec = self._graph_service._load_spec(experiment_id)
        required_pkgs = EnvironmentManager.detect_required_packages(
            graph=graph,
            spec=spec,
            explicit_packages=explicit_pkgs,
        )
        config.pip_packages = required_pkgs

        # Progress tracking setup early for build logs and container runs
        progress_log: list[ProgressEvent] = []
        self._progress_log[execution_id] = progress_log

        def on_progress(event: ProgressEvent) -> None:
            progress_log.append(event)
            print(f"[Runner] {event.event_type}: {event.message}", flush=True)

        def on_build_progress(percent: int, step: str, line: str) -> None:
            on_progress(
                ProgressEvent(
                    execution_id=execution_id,
                    event_type="docker_build",
                    message=f"[{percent}%] {step}: {line}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    details={"percent": percent, "step": step, "line": line},
                )
            )

        # Validate graph sequentially and auto-remediate safe missing declarations (device, seed, imports)
        try:
            from backend.app.graph.validator import SequentialCodeValidator
        except ModuleNotFoundError:  # pragma: no cover
            from app.graph.validator import SequentialCodeValidator

        val_report = SequentialCodeValidator.validate_graph(graph)
        if not val_report.is_valid and val_report.can_auto_remediate and val_report.remediated_code_by_node:
            new_nodes = []
            for n in graph.nodes:
                if n.id in val_report.remediated_code_by_node:
                    n_copy = DAGNode.model_validate(n.model_dump())
                    n_copy.code = val_report.remediated_code_by_node[n.id]
                    new_nodes.append(n_copy)
                else:
                    new_nodes.append(n)
            graph = GraphVersion.model_validate(graph.model_dump())
            graph.nodes = new_nodes

        # Feasibility check (unless skipped)
        feasibility: FeasibilityReport | None = None
        if not request.skip_feasibility:
            feasibility = FeasibilityChecker.check(
                graph=graph,
                docker_image=config.docker_image,
                pip_packages=config.pip_packages,
                default_timeout_seconds=config.default_timeout_seconds,
                node_timeouts={nid: nc.timeout_seconds for nid, nc in config.node_configs.items()},
            )

        # Resolve dependencies and dataset identity for provenance
        resolved_deps = EnvironmentManager.resolve_dependencies(config.pip_packages)
        dataset_identity = feasibility.dataset_checks if feasibility else FeasibilityChecker._check_datasets(graph)

        # Create manifest
        manifest = ExecutionManifest(
            execution_id=execution_id,
            experiment_id=experiment_id,
            graph_version_id=graph.version_id,
            graph_hash=graph.graph_hash or graph.compute_graph_hash(),
            config=config,
            resolved_dependencies=resolved_deps,
            docker_image_digest=f"{config.docker_image}@pinned",
            dataset_identity=dataset_identity,
            feasibility=feasibility,
            hardware=feasibility.resource_assessment if feasibility else FeasibilityChecker._assess_resources(),
            status=ExecutionStatus.running,
            created_at=datetime.now(timezone.utc).isoformat(),
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        # Create seed runs
        manifest.seed_runs = SeedCoordinator.create_seed_runs(seeds)
        self._results.save_manifest(manifest)

        def _run_execution_steps():
            try:
                # Ensure all dependencies are installed in Docker image BEFORE containers start executing
                prepared_image = EnvironmentManager.prepare_image(
                    packages=required_pkgs,
                    base_image=config.docker_image,
                    experiment_id=experiment_id,
                    on_progress=on_build_progress,
                )
                config.docker_image = prepared_image
                manifest.config.docker_image = prepared_image
                manifest.docker_image_digest = f"{prepared_image}@pinned"
                if self._docker_worker:
                    self._docker_worker._docker_image = prepared_image

                # Set up execution infrastructure
                work_dir = self._get_work_dir(experiment_id, execution_id)
                cache_dir = self._artifacts_dir / "experiments" / experiment_id / "cache"
                cache = ExecutionCache(cache_dir)

                executor = GraphExecutor(
                    work_dir=work_dir,
                    cache=cache,
                    docker_worker=self._docker_worker,
                    config=config,
                    on_progress=on_progress,
                )
                self._active_executors[execution_id] = executor

                for i, seed_run in enumerate(manifest.seed_runs):
                    if executor._cancelled:
                        seed_run.status = RunStatus.cancelled
                        continue

                    result = executor.execute_seed(graph, seed_run.seed)
                    manifest.seed_runs[i] = result

                    # Save intermediate progress
                    self._results.save_manifest(manifest)

                # Finalize
                final_manifest = self._results.finalize_manifest(manifest)
                return final_manifest
            finally:
                self._active_executors.pop(execution_id, None)

        if getattr(request, "async_run", False):
            thread = threading.Thread(target=_run_execution_steps, daemon=True)
            thread.start()
            return manifest
        else:
            return _run_execution_steps()

    # ------------------------------------------------------------------
    # Status / results
    # ------------------------------------------------------------------
    def get_execution_status(
        self, experiment_id: str, execution_id: str
    ) -> ExecutionManifest | None:
        """Get the current status of an execution."""
        return self._results.load_manifest(experiment_id, execution_id)

    def get_latest_execution(self, experiment_id: str) -> ExecutionManifest | None:
        """Get the latest execution for an experiment."""
        exec_id = self._results.get_latest_execution_id(experiment_id)
        if exec_id is None:
            return None
        return self._results.load_manifest(experiment_id, exec_id)

    def list_executions(self, experiment_id: str) -> list[dict[str, Any]]:
        """List all executions for an experiment."""
        return self._results.list_executions(experiment_id)

    def get_seed_results(
        self, experiment_id: str, execution_id: str, seed: int | None = None
    ) -> list[dict[str, Any]]:
        """Get per-seed results, optionally filtered to a specific seed."""
        manifest = self._results.load_manifest(experiment_id, execution_id)
        if manifest is None:
            return []

        results = []
        for sr in manifest.seed_runs:
            if seed is not None and sr.seed != seed:
                continue
            results.append({
                "seed": sr.seed,
                "status": sr.status.value,
                "failure_reason": sr.failure_reason.value,
                "failure_detail": sr.failure_detail,
                "started_at": sr.started_at,
                "completed_at": sr.completed_at,
                "runtime_seconds": sr.runtime_seconds,
                "metrics": sr.metrics.values if sr.metrics else {},
                "retry_count": sr.retry_count,
                "node_results": {
                    nid: {
                        "status": nr.status.value,
                        "runtime_seconds": nr.runtime_seconds,
                        "metrics": nr.metrics,
                        "cache_hit": nr.cache_hit,
                        "exit_code": nr.exit_code,
                    }
                    for nid, nr in sr.node_results.items()
                },
            })
        return results

    def get_progress(self, execution_id: str) -> list[dict[str, Any]]:
        """Get progress events for an execution."""
        events = self._progress_log.get(execution_id, [])
        return [e.model_dump() for e in events]

    # ------------------------------------------------------------------
    # Cancellation
    # ------------------------------------------------------------------
    def cancel_execution(self, execution_id: str) -> bool:
        """Cancel a running execution."""
        executor = self._active_executors.get(execution_id)
        if executor is None:
            return False
        executor.cancel()
        return True

    # ------------------------------------------------------------------
    # Resume
    # ------------------------------------------------------------------
    def resume_execution(
        self,
        experiment_id: str,
        execution_id: str,
        request: ResumeExecutionRequest,
    ) -> ExecutionManifest | None:
        """Resume a partially completed execution.

        Can retry failed seeds and/or add new seeds.
        """
        manifest = self._results.load_manifest(experiment_id, execution_id)
        if manifest is None:
            return None

        graph = self._resolve_graph(experiment_id, manifest.graph_version_id)

        # Determine which seeds to run
        seeds_to_run: list[int] = []

        if request.retry_failed:
            for sr in manifest.seed_runs:
                if sr.status not in (RunStatus.completed, RunStatus.running):
                    seeds_to_run.append(sr.seed)

        for seed in request.additional_seeds:
            if seed not in [sr.seed for sr in manifest.seed_runs]:
                manifest.seed_runs.append(
                    SeedCoordinator.create_seed_runs([seed])[0]
                )
                seeds_to_run.append(seed)

        if not seeds_to_run:
            return manifest

        # Update packages if provided in resume request
        if request.pip_packages:
            for p in request.pip_packages:
                if p not in manifest.config.pip_packages:
                    manifest.config.pip_packages.append(p)
            manifest.resolved_dependencies = EnvironmentManager.resolve_dependencies(manifest.config.pip_packages)

        # Set up progress tracking
        progress_log = self._progress_log.get(execution_id, [])
        self._progress_log[execution_id] = progress_log

        def on_progress(event: ProgressEvent) -> None:
            progress_log.append(event)
            print(f"[Runner] {event.event_type}: {event.message}", flush=True)

        def on_build_progress(percent: int, step: str, line: str) -> None:
            on_progress(
                ProgressEvent(
                    execution_id=execution_id,
                    event_type="docker_build",
                    message=f"[{percent}%] {step}: {line}",
                    timestamp=datetime.now(timezone.utc).isoformat(),
                    details={"percent": percent, "step": step, "line": line},
                )
            )

        manifest.status = ExecutionStatus.running
        self._results.save_manifest(manifest)

        def _run_resume_steps():
            try:
                # Ensure dependencies image is prepared before resuming
                prepared_image = EnvironmentManager.prepare_image(
                    packages=manifest.config.pip_packages,
                    base_image=manifest.config.docker_image,
                    experiment_id=experiment_id,
                    on_progress=on_build_progress,
                )
                manifest.config.docker_image = prepared_image
                if self._docker_worker:
                    self._docker_worker._docker_image = prepared_image

                # Set up executor
                work_dir = self._get_work_dir(experiment_id, execution_id)
                cache_dir = self._artifacts_dir / "experiments" / experiment_id / "cache"
                cache = ExecutionCache(cache_dir)

                executor = GraphExecutor(
                    work_dir=work_dir,
                    cache=cache,
                    docker_worker=self._docker_worker,
                    config=manifest.config,
                    on_progress=on_progress,
                )
                self._active_executors[execution_id] = executor

                # Re-run the seeds
                for i, sr in enumerate(manifest.seed_runs):
                    if executor._cancelled:
                        sr.status = RunStatus.cancelled
                        continue
                    if sr.seed in seeds_to_run:
                        result = executor.execute_seed(graph, sr.seed)
                        manifest.seed_runs[i] = result
                        self._results.save_manifest(manifest)

                # Finalize
                final_manifest = self._results.finalize_manifest(manifest)
                return final_manifest
            finally:
                self._active_executors.pop(execution_id, None)

        if getattr(request, "async_run", False):
            thread = threading.Thread(target=_run_resume_steps, daemon=True)
            thread.start()
            return manifest
        else:
            return _run_resume_steps()

    # ------------------------------------------------------------------
    # Evidence for audit
    # ------------------------------------------------------------------
    def get_run_evidence(
        self, experiment_id: str, execution_id: str
    ) -> dict[str, Any] | None:
        """Build evidence from execution results for audit module."""
        manifest = self._results.load_manifest(experiment_id, execution_id)
        if manifest is None:
            return None
        return self._results.build_run_evidence(manifest)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _resolve_graph(
        self, experiment_id: str, version_id: str | None = None
    ) -> GraphVersion:
        if version_id:
            graph = self._graph_service.get_version(experiment_id, version_id)
        else:
            graph = self._graph_service.get_or_create_graph(experiment_id)

        if graph is None:
            raise ValueError(f"Experiment {experiment_id} or version {version_id} not found")
        return graph

    def _get_work_dir(self, experiment_id: str, execution_id: str) -> Path:
        d = (self._artifacts_dir / "experiments" / experiment_id / "executions" / execution_id / "work").resolve()
        d.mkdir(parents=True, exist_ok=True)
        return d
