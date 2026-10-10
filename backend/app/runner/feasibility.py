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
    ) -> FeasibilityReport:
        resources = cls._assess_resources()
        requirements = cls._estimate_requirements(graph)
        dep_checks = cls._check_dependencies(pip_packages or [])
        dataset_checks = cls._check_datasets(graph)

        reasons: list[str] = []
        warnings: list[str] = []

        # Docker availability is critical
        if not resources.docker_available:
            reasons.append(
                "Docker is not available on this host. "
                "All experiment code runs inside Docker containers for isolation."
            )

        # Memory check
        total_ram_needed = sum(r.estimated_ram_mb for r in requirements)
        if resources.ram_mb > 0 and total_ram_needed > resources.ram_mb:
            warnings.append(
                f"Total estimated RAM needed ({total_ram_needed} MB) exceeds "
                f"available ({resources.ram_mb} MB). Nodes will be run "
                f"sequentially but may swap or OOM."
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
        if gpu_required and not resources.gpu_available:
            warnings.append(
                "One or more nodes require GPU but no GPU was detected. "
                "Execution will proceed on CPU, which may affect runtime and "
                "numerical results. This is reported, not silently hidden."
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
            if platform.system() == "Linux":
                with open("/proc/meminfo") as f:
                    for line in f:
                        if line.startswith("MemAvailable:"):
                            ram_mb = int(line.split()[1]) // 1024
                            break
            elif platform.system() == "Darwin":
                out = subprocess.check_output(["sysctl", "-n", "hw.memsize"], text=True)
                ram_mb = int(out.strip()) // (1024 * 1024)
        except Exception:
            pass

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
    def _estimate_requirements(cls, graph: GraphVersion) -> list[ResourceRequirement]:
        reqs: list[ResourceRequirement] = []
        for node in graph.nodes:
            requires_gpu = cls._node_needs_gpu(node)
            # Rough heuristics per node type
            ram = 512
            disk = 128
            runtime = 300
            ntype = node.type.lower()
            if "train" in ntype or "model" in ntype:
                ram = 2048
                runtime = 900
            elif "data" in ntype or "preprocess" in ntype:
                ram = 1024
                disk = 512
                runtime = 180
            elif "eval" in ntype or "metric" in ntype:
                ram = 1024
                runtime = 120

            reqs.append(
                ResourceRequirement(
                    node_id=node.id,
                    estimated_ram_mb=ram,
                    estimated_disk_mb=disk,
                    requires_gpu=requires_gpu,
                    estimated_runtime_seconds=runtime,
                )
            )
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
