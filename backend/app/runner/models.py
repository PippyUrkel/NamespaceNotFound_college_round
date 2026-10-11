"""Pydantic models for the CrisisGrid Experiment Runner.

Defines execution manifests, run results, seed runs, feasibility reports,
and all status/failure enumerations. Follows the same conventions as
graph.models — no database, all JSON-persisted.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field, model_validator


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------
class RunStatus(str, Enum):
    """Lifecycle status of an individual seed run."""
    pending = "pending"
    queued = "queued"
    preparing = "preparing"
    running = "running"
    completed = "completed"
    failed = "failed"
    timed_out = "timed_out"
    cancelled = "cancelled"
    resource_exhausted = "resource_exhausted"


class FailureReason(str, Enum):
    """Categorised cause of a run failure."""
    none = "none"
    timeout = "timeout"
    oom = "oom"
    dependency_failure = "dependency_failure"
    invalid_configuration = "invalid_configuration"
    container_crash = "container_crash"
    dataset_unavailable = "dataset_unavailable"
    resource_limit = "resource_limit"
    upstream_failure = "upstream_failure"
    unknown = "unknown"


class ExecutionStatus(str, Enum):
    """Overall status of an experiment execution across all seeds."""
    pending = "pending"
    feasibility_check = "feasibility_check"
    preparing = "preparing"
    running = "running"
    completed = "completed"
    partially_completed = "partially_completed"
    failed = "failed"
    cancelled = "cancelled"


class FeasibilityVerdict(str, Enum):
    feasible = "feasible"
    feasible_with_limitations = "feasible_with_limitations"
    blocked = "blocked"


# ---------------------------------------------------------------------------
# Resource & feasibility models
# ---------------------------------------------------------------------------
class ResourceAssessment(BaseModel):
    """Snapshot of available host resources."""
    cpu_cores: int = 0
    ram_mb: int = 0
    disk_mb: int = 0
    gpu_available: bool = False
    gpu_name: str | None = None
    gpu_memory_mb: int | None = None
    docker_available: bool = False
    docker_version: str | None = None


class ResourceRequirement(BaseModel):
    """Resource requirements for a single DAG node."""
    node_id: str
    estimated_ram_mb: int = 512
    estimated_disk_mb: int = 256
    requires_gpu: bool = False
    estimated_runtime_seconds: int = 300


class DependencyCheck(BaseModel):
    """Result of checking a single dependency."""
    name: str
    required_version: str | None = None
    available: bool = True
    installed_version: str | None = None
    issue: str | None = None


class DatasetCheck(BaseModel):
    """Result of checking a dataset's availability."""
    name: str
    url: str | None = None
    available: bool = True
    expected_size_mb: float | None = None
    downloaded_size_mb: float | None = None
    integrity_ok: bool | None = None
    issue: str | None = None


class FeasibilityReport(BaseModel):
    """Pre-execution feasibility assessment."""
    verdict: FeasibilityVerdict = FeasibilityVerdict.feasible
    reasons: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    resource_assessment: ResourceAssessment = Field(default_factory=ResourceAssessment)
    resource_requirements: list[ResourceRequirement] = Field(default_factory=list)
    dependency_checks: list[DependencyCheck] = Field(default_factory=list)
    dataset_checks: list[DatasetCheck] = Field(default_factory=list)
    estimated_total_runtime_seconds: int = 0
    checked_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())


# ---------------------------------------------------------------------------
# Execution configuration
# ---------------------------------------------------------------------------
class NodeExecutionConfig(BaseModel):
    """Per-node execution settings (timeouts, resource limits, retries)."""
    node_id: str
    timeout_seconds: int = 600
    max_retries: int = 1
    memory_limit_mb: int = 2048
    cpu_limit: float = 2.0
    environment: dict[str, str] = Field(default_factory=dict)


class ExecutionConfig(BaseModel):
    """Top-level execution configuration for an experiment run."""
    seeds: list[int] = Field(default_factory=lambda: [42])
    default_timeout_seconds: int = 600
    execution_timeout_seconds: int = 3600
    default_memory_limit_mb: int = 2048
    default_cpu_limit: float = 2.0
    max_retries: int = 1
    enable_cache: bool = True
    node_configs: dict[str, NodeExecutionConfig] = Field(default_factory=dict)
    docker_image: str = "python:3.11-slim"
    pip_packages: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Per-seed run result
# ---------------------------------------------------------------------------
class SeedRunMetrics(BaseModel):
    """Metrics collected from a single seed run."""
    values: dict[str, float] = Field(default_factory=dict)
    raw_output: str = ""
    artifacts: list[str] = Field(default_factory=list)

    @model_validator(mode="before")
    @classmethod
    def parse_metrics_input(cls, data: Any) -> Any:
        if isinstance(data, dict):
            if "values" not in data and not any(k in data for k in ("raw_output", "artifacts")):
                return {"values": data}
        return data


class SeedRun(BaseModel):
    """Result of executing the entire graph once with a specific seed."""
    seed: int
    status: RunStatus = RunStatus.pending
    failure_reason: FailureReason = FailureReason.none
    failure_detail: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    runtime_seconds: float | None = None
    metrics: SeedRunMetrics = Field(default_factory=SeedRunMetrics)
    node_results: dict[str, NodeRunResult] = Field(default_factory=dict)
    resource_usage: ResourceUsage = Field(default_factory=lambda: ResourceUsage())
    retry_count: int = 0


class NodeRunResult(BaseModel):
    """Result of running a single node in one seed run."""
    node_id: str
    status: RunStatus = RunStatus.pending
    failure_reason: FailureReason = FailureReason.none
    failure_detail: str | None = None
    started_at: str | None = None
    completed_at: str | None = None
    runtime_seconds: float | None = None
    stdout: str = ""
    stderr: str = ""
    exit_code: int | None = None
    output_files: list[str] = Field(default_factory=list)
    metrics: dict[str, float] = Field(default_factory=dict)
    cache_hit: bool = False
    cache_key: str | None = None


class ResourceUsage(BaseModel):
    """Resource usage stats for a run."""
    peak_ram_mb: float | None = None
    avg_cpu_percent: float | None = None
    disk_used_mb: float | None = None


# ---------------------------------------------------------------------------
# Aggregated metrics (only from completed runs)
# ---------------------------------------------------------------------------
class AggregatedMetric(BaseModel):
    """Aggregated metric from valid completed seed runs only."""
    metric_name: str
    values: list[float] = Field(default_factory=list)
    seeds: list[int] = Field(default_factory=list)
    mean: float | None = None
    std: float | None = None
    min_val: float | None = None
    max_val: float | None = None
    num_completed: int = 0
    num_total: int = 0
    is_complete: bool = False
    note: str = ""


# ---------------------------------------------------------------------------
# Execution manifest — full provenance record
# ---------------------------------------------------------------------------
class ExecutionManifest(BaseModel):
    """Immutable record of an experiment execution for provenance/audit."""
    execution_id: str
    experiment_id: str
    graph_version_id: str
    graph_hash: str
    config: ExecutionConfig = Field(default_factory=ExecutionConfig)
    resolved_dependencies: list[DependencyCheck] = Field(default_factory=list)
    docker_image_digest: str | None = None
    dataset_identity: list[DatasetCheck] = Field(default_factory=list)
    hardware: ResourceAssessment = Field(default_factory=ResourceAssessment)
    feasibility: FeasibilityReport | None = None
    status: ExecutionStatus = ExecutionStatus.pending
    seed_runs: list[SeedRun] = Field(default_factory=list)
    aggregated_metrics: list[AggregatedMetric] = Field(default_factory=list)
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    started_at: str | None = None
    completed_at: str | None = None
    total_runtime_seconds: float | None = None
    error_summary: str | None = None

    def compute_manifest_hash(self) -> str:
        payload = {
            "execution_id": self.execution_id,
            "experiment_id": self.experiment_id,
            "graph_version_id": self.graph_version_id,
            "graph_hash": self.graph_hash,
            "seeds": self.config.seeds,
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Imports preview and verification models
# ---------------------------------------------------------------------------
class ImportItem(BaseModel):
    """An imported module or package detected in DAG nodes."""
    module: str
    package: str
    nodes: list[str] = Field(default_factory=list)
    import_statements: list[str] = Field(default_factory=list)
    installed: bool = False
    installed_version: str | None = None
    issue: str | None = None


class EnvironmentPreview(BaseModel):
    """Pre-flight inspection of all Python imports and container readiness."""
    docker_image: str
    detected_imports: list[ImportItem] = Field(default_factory=list)
    required_packages: list[str] = Field(default_factory=list)
    all_installed: bool = True
    missing_packages: list[str] = Field(default_factory=list)
    can_preinstall: bool = True


class EnvironmentBuildProgress(BaseModel):
    """Real-time progress and build output for container image preparation."""
    experiment_id: str
    status: Literal["idle", "building", "completed", "failed"] = "idle"
    docker_image: str = ""
    packages: list[str] = Field(default_factory=list)
    current_step: str = ""
    percent: int = 0
    logs: list[str] = Field(default_factory=list)
    error: str | None = None
    started_at: str | None = None
    completed_at: str | None = None


# ---------------------------------------------------------------------------
# Submission request & progress event
# ---------------------------------------------------------------------------
class SubmitExecutionRequest(BaseModel):
    """Request to submit an experiment for execution."""
    graph_version_id: str | None = None
    seeds: list[int] | None = None
    config_overrides: dict[str, Any] = Field(default_factory=dict)
    pip_packages: list[str] | None = None
    auto_install_missing: bool = True
    skip_feasibility: bool = False
    async_run: bool = False


class ResumeExecutionRequest(BaseModel):
    """Request to resume a partially completed execution."""
    retry_failed: bool = True
    additional_seeds: list[int] = Field(default_factory=list)
    pip_packages: list[str] | None = None
    auto_install_missing: bool = True
    async_run: bool = False


class ProgressEvent(BaseModel):
    """Real-time progress event for streaming."""
    event_type: str  # node_start, node_complete, seed_start, seed_complete, etc.
    timestamp: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    seed: int | None = None
    node_id: str | None = None
    message: str = ""
    progress_percent: float | None = None
    data: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Cache models
# ---------------------------------------------------------------------------
class CacheEntry(BaseModel):
    """Record of a cached node execution result."""
    cache_key: str
    node_id: str
    seed: int
    graph_hash: str
    node_config_hash: str
    upstream_hashes: list[str] = Field(default_factory=list)
    result: NodeRunResult | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    @staticmethod
    def compute_cache_key(
        node_id: str,
        seed: int,
        node_config_hash: str,
        upstream_hashes: list[str],
    ) -> str:
        payload = {
            "node_id": node_id,
            "seed": seed,
            "node_config_hash": node_config_hash,
            "upstream": sorted(upstream_hashes),
        }
        return hashlib.sha256(
            json.dumps(payload, sort_keys=True).encode()
        ).hexdigest()[:16]


# Resolve forward refs (SeedRun references NodeRunResult)
SeedRun.model_rebuild()
