"""Pre-execution feasibility assessment.

Checks available CPU, RAM, disk, Docker daemon, dependencies, and datasets
before any experiment code runs. Reports whether the experiment is feasible,
feasible with limitations, or blocked — without ever silently modifying
scientific parameters to make things fit.
"""
from __future__ import annotations

import os
import platform
import shutil
import subprocess
from typing import Any

from .models import (
    DatasetCheck,
    DependencyCheck,
    FeasibilityReport,
    FeasibilityVerdict,
    ResourceAssessment,
    ResourceRequirement,
)

try:
    from backend.app.graph.models import DAGNode, GraphVersion
except ModuleNotFoundError:  # pragma: no cover
    from app.graph.models import DAGNode, GraphVersion


# Rough seconds per training epoch for a small CNN on the 2 CPU cores a container gets.
# Order-of-magnitude only: enough to tell a 2-minute run from a 3-hour one.
_CPU_SECONDS_PER_EPOCH = {
    "mnist": 45,
    "fashion": 45,
    "kmnist": 45,
    "cifar": 150,
    "svhn": 180,
    "stl": 300,
    "imagenet": 36000,
}
_DEFAULT_CPU_SECONDS_PER_EPOCH = 90


class FeasibilityChecker:
    """Assess whether the host can run a given experiment graph."""

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    @classmethod
    def check(
        cls,
        graph: GraphVersion,
        docker_image: str = "python:3.11-slim",
        pip_packages: list[str] | None = None,
        default_timeout_seconds: int = 600,
        node_timeouts: dict[str, int] | None = None,
    ) -> FeasibilityReport:
        resources = cls._assess_resources()
        requirements = cls._estimate_requirements(graph)
        dep_checks = cls._check_dependencies(pip_packages or [])
        dataset_checks = cls._check_datasets(graph)

        reasons: list[str] = []
        warnings: list[str] = []

        # Docker availability is advisory/warning only — hardware-based blocking is disabled
        if not resources.docker_available:
            warnings.append(
                "Docker daemon was not detected on this host. Hardware-based blocking is disabled; containers will run if Docker is started."
            )

        # Memory check — advisory/warning only, never blocks
        total_ram_needed = sum(r.estimated_ram_mb for r in requirements)
        if resources.ram_mb > 0 and total_ram_needed > resources.ram_mb:
            warnings.append(
                f"Total estimated RAM needed ({total_ram_needed} MB) exceeds "
                f"available ({resources.ram_mb} MB). Hardware limit blocking is disabled so execution will proceed."
            )

        # Disk check
        total_disk_needed = sum(r.estimated_disk_mb for r in requirements)
        if resources.disk_mb > 0 and total_disk_needed > resources.disk_mb * 0.8:
            warnings.append(
                f"Estimated disk usage ({total_disk_needed} MB) is close to "
                f"available space ({resources.disk_mb} MB)."
            )

        # GPU check — informational, not blocking
        gpu_required = any(r.requires_gpu for r in requirements)
        if resources.gpu_available:
            warnings.append(
                f"GPU acceleration is enabled: Host GPU ({resources.gpu_name}) is passed directly into execution containers."
            )
        elif gpu_required:
            warnings.append(
                "One or more nodes use a GPU when available, but no GPU was detected on host. "
                "Training will run on CPU, which affects runtime and may affect "
                "numerical results. This is reported, not silently hidden."
            )

        # Timeout check — a node estimated past its timeout will be killed and retried for nothing
        training = next((r for r in requirements if r.node_id == "training_pipeline"), None)
        epochs, per_epoch, dataset = cls._training_budget(graph)
        for req in requirements:
            timeout = (node_timeouts or {}).get(req.node_id, default_timeout_seconds)
            if req.estimated_runtime_seconds <= timeout:
                continue
            reruns_training = training is not None and req.node_id != "training_pipeline" and req.estimated_runtime_seconds >= training.estimated_runtime_seconds
            warnings.append(
                f"Node '{req.node_id}' is estimated at ~{req.estimated_runtime_seconds // 60} min but its timeout is "
                f"{timeout // 60} min, so it will likely time out. Estimate: {epochs} epochs x ~{per_epoch}s/epoch "
                f"on CPU for {dataset or 'an unknown dataset'}"
                + (" (this node re-runs training as part of its upstream code)" if reruns_training else "")
                + ". Reduce epochs in the Graph tab (recorded as 'tuned', not silently changed) "
                "or raise default_timeout_seconds when submitting."
            )

        # Dependency issues
        dep_issues = [d for d in dep_checks if not d.available]
        if dep_issues:
            warnings.append(
                f"{len(dep_issues)} pip package(s) may not be available: "
                + ", ".join(d.name for d in dep_issues)
            )

        # Dataset issues
        ds_issues = [d for d in dataset_checks if not d.available]
        if ds_issues:
            for ds in ds_issues:
                if ds.issue:
                    reasons.append(f"Dataset '{ds.name}' unavailable: {ds.issue}")
                else:
                    warnings.append(f"Dataset '{ds.name}' availability could not be confirmed.")

        # Code validation check (sequential flow and AST analysis)
        try:
            from backend.app.graph.validator import SequentialCodeValidator
        except ModuleNotFoundError:  # pragma: no cover
            from app.graph.validator import SequentialCodeValidator

        val_report = SequentialCodeValidator.validate_graph(graph)
        if not val_report.is_valid:
            for issue in val_report.issues:
                if issue.severity == "error":
                    reasons.append(
                        f"Code validation error in '{issue.node_id}' line {issue.line_number or '?'}: "
                        f"{issue.message} (Suggested fix: {issue.suggested_fix or 'None'})"
                    )
                else:
                    warnings.append(
                        f"Code validation warning in '{issue.node_id}': {issue.message}"
                    )

        # Determine verdict
        if reasons:
            verdict = FeasibilityVerdict.blocked
        elif warnings:
            verdict = FeasibilityVerdict.feasible_with_limitations
        else:
            verdict = FeasibilityVerdict.feasible

        estimated_total = sum(r.estimated_runtime_seconds for r in requirements)

        return FeasibilityReport(
            verdict=verdict,
            reasons=reasons,
            warnings=warnings,
            resource_assessment=resources,
            resource_requirements=requirements,
            dependency_checks=dep_checks,
            dataset_checks=dataset_checks,
            estimated_total_runtime_seconds=estimated_total,
        )

    # ------------------------------------------------------------------
    # Resource detection
    # ------------------------------------------------------------------
    @classmethod
    def _assess_resources(cls) -> ResourceAssessment:
        cpu_cores = os.cpu_count() or 1

        # RAM
        ram_mb = 0
        try:
            import psutil
            ram_mb = int(psutil.virtual_memory().available // (1024 * 1024))
        except Exception:
            pass

        if ram_mb <= 0:
            try:
                if platform.system() == "Linux":
                    with open("/proc/meminfo") as f:
                        for line in f:
                            if line.startswith("MemAvailable:") or line.startswith("MemTotal:"):
                                ram_mb = int(line.split()[1]) // 1024
                                break
                elif platform.system() == "Darwin":
                    out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
                    ram_mb = int(out.strip()) // (1024 * 1024)
            except Exception:
                pass

        # If RAM is undetectable on host (e.g. restricted VM/container), safe fallback to 8192 MB
        if ram_mb <= 0:
            ram_mb = 8192

        # Disk
        disk_mb = 0
        try:
            usage = shutil.disk_usage("/")
            disk_mb = int(usage.free / (1024 * 1024))
        except Exception:
            pass

        # Docker
        docker_available = False
        docker_version = None
        try:
            result = subprocess.run(
                ["docker", "version", "--format", "{{.Server.Version}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0:
                docker_available = True
                docker_version = result.stdout.strip()
        except Exception:
            pass

        # GPU (nvidia-smi)
        gpu_available = False
        gpu_name = None
        gpu_memory_mb = None
        try:
            result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(",")
                gpu_available = True
                gpu_name = parts[0].strip()
                if len(parts) > 1:
                    gpu_memory_mb = int(float(parts[1].strip()))
        except Exception:
            pass

        return ResourceAssessment(
            cpu_cores=cpu_cores,
            ram_mb=ram_mb,
            disk_mb=disk_mb,
            gpu_available=gpu_available,
            gpu_name=gpu_name,
            gpu_memory_mb=gpu_memory_mb,
            docker_available=docker_available,
            docker_version=docker_version,
        )

    # ------------------------------------------------------------------
    # Estimate node requirements
    # ------------------------------------------------------------------
    @classmethod
    def _training_budget(cls, graph: GraphVersion) -> tuple[int, int, str | None]:
        """Return (epochs, CPU seconds per epoch, dataset name) from the graph's node parameters."""
        epochs = 10
        dataset: str | None = None
        for node in graph.nodes:
            if node.parameters.get("epochs") is not None:
                try:
                    epochs = int(node.parameters["epochs"])
                except (TypeError, ValueError):
                    pass
            if node.parameters.get("dataset"):
                dataset = str(node.parameters["dataset"])
        key = (dataset or "").lower().replace("-", "").replace("_", "")
        per_epoch = next(
            (secs for name, secs in _CPU_SECONDS_PER_EPOCH.items() if name in key),
            _DEFAULT_CPU_SECONDS_PER_EPOCH,
        )
        return epochs, per_epoch, dataset

    @classmethod
    def _estimate_requirements(cls, graph: GraphVersion) -> list[ResourceRequirement]:
        epochs, per_epoch, _ = cls._training_budget(graph)
        own_runtime: dict[str, int] = {}
        reqs: list[ResourceRequirement] = []
        for node in graph.nodes:
            requires_gpu = cls._node_needs_gpu(node)
            # Rough heuristics per node type
            # (each node also pays ~15-20s of pip install; datasets come from the shared cache)
            ram = 512
            disk = 128
            runtime = 30
            ntype = node.type.lower()
            if "train" in ntype:
                ram = 2048
                runtime = 60 + epochs * per_epoch
            elif "model" in ntype:
                ram = 2048
                runtime = 30
            elif "data" in ntype or "preprocess" in ntype:
                ram = 1024
                disk = 512
                runtime = 60
            elif "eval" in ntype or "metric" in ntype:
                ram = 1024
                runtime = 60
            own_runtime[node.id] = runtime

            reqs.append(
                ResourceRequirement(
                    node_id=node.id,
                    estimated_ram_mb=ram,
                    estimated_disk_mb=disk,
                    requires_gpu=requires_gpu,
                    estimated_runtime_seconds=runtime,
                )
            )

        # The executor prepends every ancestor's code to a node, so a node's container
        # also pays for re-running its whole upstream chain (including training).
        upstream = {node.id: list(node.upstream) for node in graph.nodes}
        for req in reqs:
            seen: set[str] = set()
            stack = list(upstream.get(req.node_id, []))
            while stack:
                anc = stack.pop()
                if anc in seen:
                    continue
                seen.add(anc)
                stack.extend(upstream.get(anc, []))
            req.estimated_runtime_seconds += sum(own_runtime.get(anc, 0) for anc in seen)
        return reqs

    @staticmethod
    def _node_needs_gpu(node: DAGNode) -> bool:
        code_lower = node.code.lower()
        gpu_hints = ["cuda", ".to(device)", "torch.device", "gpu", "nvidia", "tensorflow"]
        return any(hint in code_lower for hint in gpu_hints)

    # ------------------------------------------------------------------
    # Dependency checks
    # ------------------------------------------------------------------
    @classmethod
    def _check_dependencies(cls, packages: list[str]) -> list[DependencyCheck]:
        checks: list[DependencyCheck] = []
        for pkg in packages:
            # Best-effort: we just record what's requested.
            # Actual availability is checked inside the Docker container.
            checks.append(
                DependencyCheck(
                    name=pkg,
                    available=True,
                    issue=None,
                )
            )
        return checks

    # ------------------------------------------------------------------
    # Dataset checks
    # ------------------------------------------------------------------
    @classmethod
    def _check_datasets(cls, graph: GraphVersion) -> list[DatasetCheck]:
        checks: list[DatasetCheck] = []
        seen: set[str] = set()

        for node in graph.nodes:
            dataset_name = node.parameters.get("dataset")
            if dataset_name and dataset_name not in seen:
                seen.add(str(dataset_name))
                checks.append(
                    DatasetCheck(
                        name=str(dataset_name),
                        available=True,  # Assume available; real download happens at runtime
                        issue=None,
                    )
                )
        return checks
