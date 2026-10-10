"""Results collector — persists execution manifests and collects evidence.

Aggregates results from completed seed runs, persists the full execution
manifest as JSON, and provides evidence for the audit/verification modules.

Key guarantees:
- Execution status is separate from scientific verdicts
- Hardware limitations or incomplete runs do NOT automatically imply
  that a paper's findings are false
- Failed runs are never treated as zero-valued measurements
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .models import (
    AggregatedMetric,
    ExecutionManifest,
    ExecutionStatus,
    RunStatus,
    SeedRun,
)
from .seed_coordinator import SeedCoordinator


class ResultsCollector:
    """Collect, aggregate, and persist experiment execution results."""

    def __init__(self, artifacts_dir: Path) -> None:
        self._artifacts_dir = artifacts_dir

    # ------------------------------------------------------------------
    # Manifest persistence
    # ------------------------------------------------------------------
    def save_manifest(self, manifest: ExecutionManifest) -> Path:
        """Persist execution manifest to JSON file."""
        exec_dir = self._get_execution_dir(manifest.experiment_id, manifest.execution_id)
        exec_dir.mkdir(parents=True, exist_ok=True)
        manifest_path = exec_dir / "execution_manifest.json"
        manifest_path.write_text(
            json.dumps(manifest.model_dump(), indent=2),
            encoding="utf-8",
        )
        # Also update the latest manifest pointer
        latest_path = (
            self._artifacts_dir
            / "experiments"
            / manifest.experiment_id
            / "latest_execution.json"
        )
        latest_path.write_text(
            json.dumps({"execution_id": manifest.execution_id}, indent=2),
            encoding="utf-8",
        )
        return manifest_path

    def load_manifest(self, experiment_id: str, execution_id: str) -> ExecutionManifest | None:
        """Load an execution manifest from disk."""
        path = self._get_execution_dir(experiment_id, execution_id) / "execution_manifest.json"
        if not path.exists():
            return None
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return ExecutionManifest.model_validate(data)
        except Exception:
            return None

    def list_executions(self, experiment_id: str) -> list[dict[str, Any]]:
        """List all executions for an experiment."""
        exec_root = self._artifacts_dir / "experiments" / experiment_id / "executions"
        if not exec_root.exists():
            return []
        executions = []
        for entry in sorted(exec_root.iterdir()):
            if entry.is_dir():
                manifest_path = entry / "execution_manifest.json"
                if manifest_path.exists():
                    try:
                        data = json.loads(manifest_path.read_text(encoding="utf-8"))
                        executions.append({
                            "execution_id": data.get("execution_id"),
                            "status": data.get("status"),
                            "graph_version_id": data.get("graph_version_id"),
                            "created_at": data.get("created_at"),
                            "completed_at": data.get("completed_at"),
                            "total_runtime_seconds": data.get("total_runtime_seconds"),
                            "seed_count": len(data.get("seed_runs", [])),
                        })
                    except Exception:
                        pass
        return executions

    def get_latest_execution_id(self, experiment_id: str) -> str | None:
        """Get the latest execution ID for an experiment."""
        latest_path = self._artifacts_dir / "experiments" / experiment_id / "latest_execution.json"
        if not latest_path.exists():
            return None
        try:
            data = json.loads(latest_path.read_text(encoding="utf-8"))
            return data.get("execution_id")
        except Exception:
            return None

    # ------------------------------------------------------------------
    # Result finalization
    # ------------------------------------------------------------------
    def finalize_manifest(self, manifest: ExecutionManifest) -> ExecutionManifest:
        """Finalize the manifest: aggregate metrics, determine status, save."""
        # Aggregate metrics from completed seed runs
        manifest.aggregated_metrics = SeedCoordinator.aggregate_metrics(manifest.seed_runs)

        # Determine overall status
        manifest.status = self._determine_status(manifest.seed_runs)
        manifest.completed_at = datetime.now(timezone.utc).isoformat()

        if manifest.started_at:
            try:
                t1 = datetime.fromisoformat(manifest.started_at)
                t2 = datetime.fromisoformat(manifest.completed_at)
                manifest.total_runtime_seconds = (t2 - t1).total_seconds()
            except Exception:
                pass

        # Generate error summary if needed
        manifest.error_summary = self._build_error_summary(manifest)

        # Save
        self.save_manifest(manifest)
        return manifest

    # ------------------------------------------------------------------
    # Evidence for audit/verification
    # ------------------------------------------------------------------
    def build_run_evidence(self, manifest: ExecutionManifest) -> dict[str, Any]:
        """Build evidence record for the audit module.

        IMPORTANT: Execution status is SEPARATE from scientific verdicts.
        Hardware limitations or incomplete runs do NOT automatically imply
        that a paper's findings are false.
        """
        summary = SeedCoordinator.summarize_runs(manifest.seed_runs)

        evidence: dict[str, Any] = {
            "execution_id": manifest.execution_id,
            "graph_version_id": manifest.graph_version_id,
            "graph_hash": manifest.graph_hash,
            "status": manifest.status.value,
            "seeds_total": summary["total_seeds"],
            "seeds_completed": summary["status_counts"].get("completed", 0),
            "all_seeds_completed": summary["all_completed"],
            "aggregated_metrics": [m.model_dump() for m in manifest.aggregated_metrics],
            "hardware": manifest.hardware.model_dump(),
            "execution_limitations": [],
        }

        # Note limitations without making scientific claims
        if not summary["all_completed"]:
            evidence["execution_limitations"].append({
                "type": "incomplete_execution",
                "detail": (
                    f"Only {summary['status_counts'].get('completed', 0)}/{summary['total_seeds']} "
                    f"seeds completed successfully. Incomplete results should not be used "
                    f"to conclude that the paper's claims are false."
                ),
                "failure_reasons": summary["failure_reasons"],
            })

        if not manifest.hardware.gpu_available:
            evidence["execution_limitations"].append({
                "type": "no_gpu",
                "detail": (
                    "Execution ran on CPU only. Results may differ from GPU execution "
                    "due to floating-point non-determinism across hardware."
                ),
            })

        # Per-seed results for detailed audit
        evidence["per_seed_results"] = []
        for sr in manifest.seed_runs:
            seed_evidence = {
                "seed": sr.seed,
                "status": sr.status.value,
                "metrics": sr.metrics.values if sr.metrics else {},
                "runtime_seconds": sr.runtime_seconds,
            }
            if sr.failure_reason.value != "none":
                seed_evidence["failure_reason"] = sr.failure_reason.value
                seed_evidence["failure_detail"] = sr.failure_detail
            evidence["per_seed_results"].append(seed_evidence)

        return evidence

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _get_execution_dir(self, experiment_id: str, execution_id: str) -> Path:
        return self._artifacts_dir / "experiments" / experiment_id / "executions" / execution_id

    @staticmethod
    def _determine_status(seed_runs: list[SeedRun]) -> ExecutionStatus:
        if not seed_runs:
            return ExecutionStatus.pending

        statuses = {sr.status for sr in seed_runs}

        if all(sr.status == RunStatus.completed for sr in seed_runs):
            return ExecutionStatus.completed
        elif any(sr.status == RunStatus.completed for sr in seed_runs):
            return ExecutionStatus.partially_completed
        elif any(sr.status == RunStatus.cancelled for sr in seed_runs):
            return ExecutionStatus.cancelled
        elif all(sr.status in (RunStatus.failed, RunStatus.timed_out, RunStatus.resource_exhausted) for sr in seed_runs):
            return ExecutionStatus.failed
        elif any(sr.status == RunStatus.running for sr in seed_runs):
            return ExecutionStatus.running
        else:
            return ExecutionStatus.failed

    @staticmethod
    def _build_error_summary(manifest: ExecutionManifest) -> str | None:
        failed_runs = [
            sr for sr in manifest.seed_runs
            if sr.status not in (RunStatus.completed, RunStatus.pending, RunStatus.running)
        ]
        if not failed_runs:
            return None

        parts: list[str] = []
        for sr in failed_runs:
            parts.append(
                f"Seed {sr.seed}: {sr.status.value}"
                + (f" ({sr.failure_reason.value})" if sr.failure_reason.value != "none" else "")
                + (f" — {sr.failure_detail}" if sr.failure_detail else "")
            )
        return "; ".join(parts)
