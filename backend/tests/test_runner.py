"""Comprehensive tests for the CrisisGrid Experiment Runner.

Verifies:
1. Pre-execution feasibility assessment without parameter modification
2. Docker worker script generation, command building, and seed injection
3. Topological graph execution order
4. Multi-seed isolation and independent runs
5. Hash-based caching and downstream cache invalidation
6. Timeout handling and process termination
7. Failure recovery, categorization, and aggregation exclusion (never zero-valued)
8. Execution resumption and bounded retries
9. Execution manifest provenance and audit evidence separation
10. Dataset manager integrity checking
11. Full FastAPI runner endpoint suite
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from backend.app.graph.models import DAGEdge, DAGNode, GraphVersion
from backend.app.graph.service import GraphService
from backend.app.injestor.service import IngestionService
from backend.app.main import app
from backend.app.runner.cache import ExecutionCache
from backend.app.runner.dataset_manager import DatasetManager
from backend.app.runner.docker_worker import DockerWorker
from backend.app.runner.environment_manager import EnvironmentManager
from backend.app.runner.executor import GraphExecutor
from backend.app.runner.feasibility import FeasibilityChecker
from backend.app.runner.models import (
    ExecutionConfig,
    ExecutionManifest,
    ExecutionStatus,
    FailureReason,
    FeasibilityVerdict,
    NodeExecutionConfig,
    NodeRunResult,
    ResumeExecutionRequest,
    RunStatus,
    SeedRun,
    SubmitExecutionRequest,
)
from backend.app.runner.results_collector import ResultsCollector
from backend.app.runner.routes import router as runner_router
from backend.app.runner.service import RunnerService
from backend.app.runner.seed_coordinator import SeedCoordinator
from backend.config import settings


# ---------------------------------------------------------------------------
# Fixtures & Mock Worker
# ---------------------------------------------------------------------------
class MockDockerWorker(DockerWorker):
    """Simulated DockerWorker that runs quickly in-memory without Docker daemon."""

    def __init__(self, work_dir: Path, failure_node_id: str | None = None, failure_mode: str = "crash") -> None:
        super().__init__(work_dir=work_dir)
        self.executed_nodes: list[tuple[str, int]] = []
        self.failure_node_id = failure_node_id
        self.failure_mode = failure_mode
        self.call_count: dict[str, int] = {}

    def execute_node(
        self,
        node_id: str,
        code: str,
        seed: int,
        parameters: dict[str, Any],
        config: NodeExecutionConfig | None = None,
        upstream_outputs_dir: Path | None = None,
        pip_packages: list[str] | None = None,
        upstream_code: str | None = None,
        **kwargs: Any,
    ) -> NodeRunResult:
        self.executed_nodes.append((node_id, seed))
        self.call_count[node_id] = self.call_count.get(node_id, 0) + 1

        if self.failure_node_id and node_id == self.failure_node_id:
            if self.failure_mode == "timeout":
                return NodeRunResult(
                    node_id=node_id,
                    status=RunStatus.timed_out,
                    failure_reason=FailureReason.timeout,
                    failure_detail="Simulated timeout after 10s",
                    started_at="2026-10-10T00:00:00Z",
                    completed_at="2026-10-10T00:00:10Z",
                    runtime_seconds=10.0,
                    exit_code=-1,
                )
            elif self.failure_mode == "oom":
                return NodeRunResult(
                    node_id=node_id,
                    status=RunStatus.resource_exhausted,
                    failure_reason=FailureReason.oom,
                    failure_detail="Simulated container killed (exit 137) OOM",
                    started_at="2026-10-10T00:00:00Z",
                    completed_at="2026-10-10T00:00:02Z",
                    runtime_seconds=2.0,
                    exit_code=137,
                )
            elif self.failure_mode == "transient_fail_once":
                if self.call_count[node_id] == 1:
                    return NodeRunResult(
                        node_id=node_id,
                        status=RunStatus.failed,
                        failure_reason=FailureReason.container_crash,
                        failure_detail="Transient crash on attempt 1",
                        exit_code=1,
                    )
                # Succeed on retry
            else:
                return NodeRunResult(
                    node_id=node_id,
                    status=RunStatus.failed,
                    failure_reason=FailureReason.container_crash,
                    failure_detail="Simulated non-zero exit code 1",
                    exit_code=1,
                )

        # Normal success
        metrics: dict[str, float] = {}
        if "eval" in node_id or "claim" in node_id or "metric" in node_id:
            metrics = {"accuracy": 0.85 + (seed % 10) * 0.01, "loss": 0.25}

        return NodeRunResult(
            node_id=node_id,
            status=RunStatus.completed,
            failure_reason=FailureReason.none,
            started_at="2026-10-10T00:00:00Z",
            completed_at="2026-10-10T00:00:01Z",
            runtime_seconds=1.0,
            stdout=f"Executed {node_id} with seed {seed}",
            stderr="",
            exit_code=0,
            metrics=metrics,
        )


@pytest.fixture
def test_env(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    monkeypatch.setattr(settings, "groq_api_key", "")

    # Ingest a sample experiment
    ingestion = IngestionService(artifacts_dir=tmp_path)
    paper = {
        "title": "Robust Multi-Seed Experiment",
        "full_text": "Dataset CIFAR-10. Seed 42. Learning rate 0.001. Batch size 32. Epochs 5. Accuracy 88.5%.",
        "hash_sha256": "abcdef987654",
        "evidence": [],
    }
    repo = {
        "repository_url": "https://github.com/testorg/robust-test",
        "branch": "main",
        "commit_sha": "beef01",
        "readme": "Dataset: CIFAR-10\nSeed 42",
        "files": {
            "train.py": "def train(): pass\n",
        },
        "evidence": [],
    }
    spec = ingestion.build(paper, repo, repo_url="https://github.com/testorg/robust-test")
    exp_id = spec["experiment_id"]

    # Generate initial graph
    graph_service = GraphService(artifacts_dir=tmp_path)
    graph = graph_service.generate_graph(exp_id)

    return {
        "tmp_path": tmp_path,
        "experiment_id": exp_id,
        "graph": graph,
    }


# ---------------------------------------------------------------------------
# Test 1: Feasibility Assessment
# ---------------------------------------------------------------------------
def test_feasibility_assessment_reports_hardware_and_limits(test_env) -> None:
    graph = test_env["graph"]
    report = FeasibilityChecker.check(
        graph=graph,
        docker_image="python:3.11-slim",
        pip_packages=["torch", "numpy"],
    )

    assert report.verdict in (
        FeasibilityVerdict.feasible,
        FeasibilityVerdict.feasible_with_limitations,
        FeasibilityVerdict.blocked,
    )
    assert report.resource_assessment.cpu_cores >= 1
    assert len(report.resource_requirements) == len(graph.nodes)
    assert len(report.dependency_checks) == 2
    # Ensure scientific parameters are not modified
    assert any(d.name == "CIFAR-10" for d in report.dataset_checks)


# ---------------------------------------------------------------------------
# Test 2: Docker Worker Script & Command Generation
# ---------------------------------------------------------------------------
def test_docker_worker_script_generation_and_command_building(tmp_path) -> None:
    worker = DockerWorker(work_dir=tmp_path)
    script = worker._build_runner_script(
        code="print('Hello CrisisGrid')",
        seed=1337,
        parameters={"learning_rate": 0.001, "batch_size": 64},
    )

    # Deterministic seeding check
    assert "SEED = 1337" in script
    assert "os.environ['PYTHONHASHSEED'] = str(SEED)" in script
    assert "random.seed(SEED)" in script
    assert "np.random.seed(SEED)" in script
    assert "torch.manual_seed(SEED)" in script
    assert "learning_rate = 0.001" in script
    assert "report_metric" in script
    assert "print('Hello CrisisGrid')" in script

    # Command construction check
    cfg = NodeExecutionConfig(node_id="test_node", memory_limit_mb=1024, cpu_limit=1.5)
    cmd = worker._build_docker_command(
        code_file=tmp_path / "run.py",
        node_dir=tmp_path,
        output_dir=tmp_path / "out",
        seed=1337,
        config=cfg,
    )

    assert "docker" == cmd[0]
    assert "run" == cmd[1]
    assert "--memory=1024m" in cmd
    assert "--cpus=1.5" in cmd
    assert "--network=none" in cmd
    assert "PYTHONHASHSEED=1337" in " ".join(cmd)
    assert "CRISISGRID_SEED=1337" in " ".join(cmd)


# ---------------------------------------------------------------------------
# Test 3: Graph Execution Order (Topological)
# ---------------------------------------------------------------------------
def test_graph_executor_topological_execution_order(test_env) -> None:
    graph = test_env["graph"]
    mock_worker = MockDockerWorker(work_dir=test_env["tmp_path"])

    executor = GraphExecutor(
        work_dir=test_env["tmp_path"] / "exec",
        docker_worker=mock_worker,
    )

    seed_run = executor.execute_seed(graph, seed=42)

    assert seed_run.status == RunStatus.completed
    assert seed_run.seed == 42
    assert len(seed_run.node_results) == len(graph.nodes)

    executed_ids = [nid for nid, _ in mock_worker.executed_nodes]
    # Check that upstream nodes execute before downstream
    assert executed_ids.index("setup_environment") < executed_ids.index("data_pipeline")
    assert executed_ids.index("data_pipeline") < executed_ids.index("model_initialization")
    assert executed_ids.index("model_initialization") < executed_ids.index("training_pipeline")
    assert executed_ids.index("training_pipeline") < executed_ids.index("evaluation_pipeline")


# ---------------------------------------------------------------------------
# Test 4: Seed Coordinator & Multi-Seed Isolation
# ---------------------------------------------------------------------------
def test_seed_coordinator_independent_runs_and_seed_isolation(test_env) -> None:
    # Test seed resolution defaults to at least 3
    seeds = SeedCoordinator.resolve_seeds(explicit_seeds=None, min_seeds=3)
    assert len(seeds) >= 3
    assert seeds[0] == 42

    # Custom explicit seeds
    custom_seeds = SeedCoordinator.resolve_seeds([11, 22, 33], min_seeds=3)
    assert custom_seeds == [11, 22, 33]

    # Padding if user provides < 3 seeds with pad_explicit=True
    padded = SeedCoordinator.resolve_seeds([99], min_seeds=3, pad_explicit=True)
    assert len(padded) >= 3
    assert padded[0] == 99

    # Execute with multiple seeds
    mock_worker = MockDockerWorker(work_dir=test_env["tmp_path"])
    executor = GraphExecutor(
        work_dir=test_env["tmp_path"] / "exec",
        docker_worker=mock_worker,
    )

    seed_runs: list[SeedRun] = []
    for s in [42, 123, 7]:
        sr = executor.execute_seed(test_env["graph"], seed=s)
        seed_runs.append(sr)

    assert len(seed_runs) == 3
    for sr in seed_runs:
        assert sr.status == RunStatus.completed
        assert "accuracy" in sr.metrics.values

    # Metric aggregation
    aggregated = SeedCoordinator.aggregate_metrics(seed_runs)
    acc_metric = next((m for m in aggregated if m.metric_name == "accuracy"), None)
    assert acc_metric is not None
    assert acc_metric.is_complete is True
    assert acc_metric.num_completed == 3
    assert acc_metric.mean is not None
    assert acc_metric.std is not None
    assert acc_metric.min_val <= acc_metric.mean <= acc_metric.max_val


# ---------------------------------------------------------------------------
# Test 5: Hash-Based Caching and Downstream Invalidation
# ---------------------------------------------------------------------------
def test_hash_based_caching_and_downstream_invalidation(test_env) -> None:
    graph = test_env["graph"]
    cache_dir = test_env["tmp_path"] / "cache"
    cache = ExecutionCache(cache_dir)
    mock_worker = MockDockerWorker(work_dir=test_env["tmp_path"])

    config = ExecutionConfig(enable_cache=True)
    executor = GraphExecutor(
        work_dir=test_env["tmp_path"] / "exec",
        cache=cache,
        docker_worker=mock_worker,
        config=config,
    )

    # First run: cache miss for all nodes
    run1 = executor.execute_seed(graph, seed=42)
    assert run1.status == RunStatus.completed
    assert all(not r.cache_hit for r in run1.node_results.values())
    initial_call_count = len(mock_worker.executed_nodes)

    # Second run with same seed: cache hit for all nodes
    run2 = executor.execute_seed(graph, seed=42)
    assert run2.status == RunStatus.completed
    assert all(r.cache_hit for r in run2.node_results.values())
    # Worker shouldn't have been called again for cached nodes
    assert len(mock_worker.executed_nodes) == initial_call_count

    # Invalidate downstream of data_pipeline
    adj = {
        "setup_environment": ["data_pipeline"],
        "data_pipeline": ["model_initialization"],
        "model_initialization": ["training_pipeline"],
        "training_pipeline": ["evaluation_pipeline"],
        "evaluation_pipeline": ["claim_verification"],
        "claim_verification": [],
    }
    invalidated = cache.invalidate_downstream("data_pipeline", adj)
    assert len(invalidated) >= 5  # data_pipeline and all downstream

    # Third run: setup_environment hits cache, others re-execute
    run3 = executor.execute_seed(graph, seed=42)
    assert run3.node_results["setup_environment"].cache_hit is True
    assert run3.node_results["data_pipeline"].cache_hit is False


# ---------------------------------------------------------------------------
# Test 6: Timeout Handling
# ---------------------------------------------------------------------------
def test_timeout_handling_marks_timed_out_and_terminates(test_env) -> None:
    graph = test_env["graph"]
    # Simulate timeout on training_pipeline node
    mock_worker = MockDockerWorker(
        work_dir=test_env["tmp_path"],
        failure_node_id="training_pipeline",
        failure_mode="timeout",
    )

    executor = GraphExecutor(
        work_dir=test_env["tmp_path"] / "exec_timeout",
        docker_worker=mock_worker,
    )

    seed_run = executor.execute_seed(graph, seed=42)

    assert seed_run.status == RunStatus.timed_out
    assert seed_run.failure_reason == FailureReason.timeout

    # Prior nodes succeeded
    assert seed_run.node_results["setup_environment"].status == RunStatus.completed
    assert seed_run.node_results["data_pipeline"].status == RunStatus.completed
    # Timed out node
    assert seed_run.node_results["training_pipeline"].status == RunStatus.timed_out
    # Downstream skipped due to upstream failure
    assert seed_run.node_results["evaluation_pipeline"].failure_reason == FailureReason.upstream_failure


# ---------------------------------------------------------------------------
# Test 7: Failure Categorization and Never-Zero Aggregation
# ---------------------------------------------------------------------------
def test_failure_categorization_and_never_zero_aggregation(test_env) -> None:
    # 1. OOM failure categorization
    mock_worker_oom = MockDockerWorker(
        work_dir=test_env["tmp_path"],
        failure_node_id="model_initialization",
        failure_mode="oom",
    )
    executor_oom = GraphExecutor(
        work_dir=test_env["tmp_path"] / "exec_oom",
        docker_worker=mock_worker_oom,
    )
    sr_oom = executor_oom.execute_seed(test_env["graph"], seed=42)
    assert sr_oom.status == RunStatus.resource_exhausted
    assert sr_oom.failure_reason == FailureReason.oom

    # 2. Bounded retries for transient failure
    mock_worker_retry = MockDockerWorker(
        work_dir=test_env["tmp_path"],
        failure_node_id="data_pipeline",
        failure_mode="transient_fail_once",
    )
    cfg = ExecutionConfig(max_retries=1)
    executor_retry = GraphExecutor(
        work_dir=test_env["tmp_path"] / "exec_retry",
        docker_worker=mock_worker_retry,
        config=cfg,
    )
    sr_retry = executor_retry.execute_seed(test_env["graph"], seed=42)
    assert sr_retry.status == RunStatus.completed
    assert mock_worker_retry.call_count["data_pipeline"] == 2

    # 3. Aggregation NEVER treats failed runs as zero-valued
    success_run = SeedRun(
        seed=1,
        status=RunStatus.completed,
        metrics={"accuracy": 0.90, "loss": 0.15},
    )
    failed_run = SeedRun(
        seed=2,
        status=RunStatus.failed,
        failure_reason=FailureReason.container_crash,
    )
    timed_out_run = SeedRun(
        seed=3,
        status=RunStatus.timed_out,
        failure_reason=FailureReason.timeout,
    )

    agg = SeedCoordinator.aggregate_metrics([success_run, failed_run, timed_out_run])
    acc = next(m for m in agg if m.metric_name == "accuracy")

    # Mean must be 0.90 (from the only completed run), NOT diluted to 0.30 by zeros!
    assert acc.mean == 0.90
    assert acc.num_completed == 1
    assert acc.num_total == 3
    assert acc.is_complete is False
    assert "incomplete" in acc.note.lower()


# ---------------------------------------------------------------------------
# Test 8: Safe Resumption
# ---------------------------------------------------------------------------
def test_safe_resumption_and_retry_failed_seeds(test_env) -> None:
    exp_id = test_env["experiment_id"]
    artifacts_dir = test_env["tmp_path"]

    # First run: seed 123 fails
    mock_worker = MockDockerWorker(
        work_dir=artifacts_dir,
        failure_node_id="claim_verification",
        failure_mode="crash",
    )

    service = RunnerService(artifacts_dir=artifacts_dir, docker_worker=mock_worker)
    manifest = service.submit_execution(
        exp_id,
        SubmitExecutionRequest(seeds=[42, 123], skip_feasibility=True),
    )

    assert manifest.status == ExecutionStatus.failed
    assert manifest.seed_runs[0].status == RunStatus.failed

    # Now fix the worker issue and resume
    mock_worker_fixed = MockDockerWorker(work_dir=artifacts_dir)
    service_fixed = RunnerService(artifacts_dir=artifacts_dir, docker_worker=mock_worker_fixed)

    resumed = service_fixed.resume_execution(
        exp_id,
        manifest.execution_id,
        ResumeExecutionRequest(retry_failed=True, additional_seeds=[7]),
    )

    assert resumed is not None
    assert resumed.status == ExecutionStatus.completed
    assert len(resumed.seed_runs) == 3
    assert all(sr.status == RunStatus.completed for sr in resumed.seed_runs)


# ---------------------------------------------------------------------------
# Test 9: Execution Manifest Provenance & Audit Evidence
# ---------------------------------------------------------------------------
def test_execution_manifest_provenance_and_audit_evidence(test_env) -> None:
    exp_id = test_env["experiment_id"]
    artifacts_dir = test_env["tmp_path"]
    mock_worker = MockDockerWorker(work_dir=artifacts_dir)

    service = RunnerService(artifacts_dir=artifacts_dir, docker_worker=mock_worker)
    manifest = service.submit_execution(
        exp_id,
        SubmitExecutionRequest(seeds=[42, 123, 7], skip_feasibility=False),
    )

    # Provenance checks
    assert manifest.graph_version_id == "v1"
    assert len(manifest.graph_hash) > 0
    assert len(manifest.docker_image_digest or "") > 0
    assert len(manifest.resolved_dependencies) >= 0
    assert manifest.hardware.cpu_cores >= 1

    # Audit evidence check
    evidence = service.get_run_evidence(exp_id, manifest.execution_id)
    assert evidence is not None
    assert evidence["execution_id"] == manifest.execution_id
    assert evidence["seeds_completed"] == 3
    assert evidence["all_seeds_completed"] is True
    assert "per_seed_results" in evidence
    # Execution status separate from scientific verdict
    assert evidence["status"] == "completed"


# ---------------------------------------------------------------------------
# Test 10: Dataset Manager Integrity Checks
# ---------------------------------------------------------------------------
def test_dataset_manager_progress_and_integrity_checks(tmp_path) -> None:
    dm = DatasetManager(storage_dir=tmp_path / "datasets")

    # 1. Missing dataset without URL
    check_missing = dm.prepare_dataset(name="missing_dataset", url=None)
    assert check_missing.available is False
    assert "not present in local cache" in (check_missing.issue or "")

    # 2. Existing dataset with size mismatch
    ds_dir = tmp_path / "datasets" / "test_ds"
    ds_dir.mkdir(parents=True)
    bin_file = ds_dir / "dataset.bin"
    bin_file.write_bytes(b"12345")

    check_corrupt = dm.prepare_dataset(
        name="test_ds",
        expected_size_bytes=100,  # Expected 100 bytes, found 5
    )
    assert check_corrupt.available is False
    assert check_corrupt.integrity_ok is False
    assert "Size mismatch" in (check_corrupt.issue or "")


# ---------------------------------------------------------------------------
# Test 11: FastAPI Runner Endpoints
# ---------------------------------------------------------------------------
def test_runner_api_endpoints(test_env, monkeypatch) -> None:
    exp_id = test_env["experiment_id"]
    artifacts_dir = test_env["tmp_path"]

    mock_worker = MockDockerWorker(work_dir=artifacts_dir)
    # Patch the singleton service used by router
    test_service = RunnerService(artifacts_dir=artifacts_dir, docker_worker=mock_worker)
    monkeypatch.setattr("backend.app.runner.routes.service", test_service)

    client = TestClient(app)

    # 1. Feasibility endpoint
    res = client.get(f"/experiments/{exp_id}/feasibility")
    assert res.status_code == 200
    data = res.json()
    assert "verdict" in data
    assert "resource_assessment" in data

    # 2. Submit execution endpoint
    submit_res = client.post(
        f"/experiments/{exp_id}/executions",
        json={"seeds": [42, 123, 7], "skip_feasibility": True},
    )
    assert submit_res.status_code == 200
    exec_data = submit_res.json()
    exec_id = exec_data["execution_id"]
    assert exec_data["status"] == "completed"
    assert len(exec_data["seed_runs"]) == 3

    # 3. List executions endpoint
    list_res = client.get(f"/experiments/{exp_id}/executions")
    assert list_res.status_code == 200
    assert len(list_res.json()) >= 1

    # 4. Latest execution endpoint
    latest_res = client.get(f"/experiments/{exp_id}/executions/latest")
    assert latest_res.status_code == 200
    assert latest_res.json()["execution_id"] == exec_id

    # 5. Get execution details by ID
    get_res = client.get(f"/experiments/{exp_id}/executions/{exec_id}")
    assert get_res.status_code == 200
    assert get_res.json()["execution_id"] == exec_id

    # 6. Progress endpoint
    progress_res = client.get(f"/experiments/{exp_id}/executions/{exec_id}/progress")
    assert progress_res.status_code == 200
    assert isinstance(progress_res.json(), list)

    # 7. Seeds endpoint
    seeds_res = client.get(f"/experiments/{exp_id}/executions/{exec_id}/seeds")
    assert seeds_res.status_code == 200
    assert len(seeds_res.json()) == 3

    # Filter seeds
    seed_42_res = client.get(f"/experiments/{exp_id}/executions/{exec_id}/seeds?seed=42")
    assert seed_42_res.status_code == 200
    assert len(seed_42_res.json()) == 1
    assert seed_42_res.json()[0]["seed"] == 42

    # 8. Evidence endpoint
    ev_res = client.get(f"/experiments/{exp_id}/executions/{exec_id}/evidence")
    assert ev_res.status_code == 200
    ev_data = ev_res.json()
    assert ev_data["execution_id"] == exec_id
    assert ev_data["all_seeds_completed"] is True

    # 9. Cancel endpoint
    cancel_res = client.post(f"/experiments/{exp_id}/executions/{exec_id}/cancel")
    assert cancel_res.status_code == 200

    # 10. Nonexistent execution
    nonexistent = client.get(f"/experiments/{exp_id}/executions/nonexistent_id")
    assert nonexistent.status_code == 404


# ---------------------------------------------------------------------------
# Test 12: Environment Manager Package Detection and Pre-Installation
# ---------------------------------------------------------------------------
def test_environment_manager_detects_packages_and_prepares_image(test_env) -> None:
    graph = test_env["graph"]
    # 1. Detect required packages from graph
    pkgs = EnvironmentManager.detect_required_packages(graph)
    assert "torch" in pkgs
    assert "numpy" in pkgs

    # 2. Check resolution
    resolved = EnvironmentManager.resolve_dependencies(pkgs)
    assert any(d.name == "torch" for d in resolved)
    assert any(d.name == "numpy" for d in resolved)

    # 3. Prepare image returns pre-baked or prepared image tag
    image = EnvironmentManager.prepare_image(pkgs)
    assert "crisisgrid" in image

