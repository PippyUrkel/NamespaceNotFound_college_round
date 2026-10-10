from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings

try:
    from backend.app.injestor.service import IngestionService
    from backend.app.runner.results_collector import ResultsCollector
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.service import IngestionService
    from app.runner.results_collector import ResultsCollector

from .context import build_context
from .engine import run_audit
from .llm_checks import check_ambiguous_claims
from .models import Finding, RunSummary
from .scoring import score as score_findings
from .verification import run_summaries_from_execution, verify_claims


class ExperimentNotFound(Exception):
    pass


class ExecutionNotFound(Exception):
    pass


class AuditService:
    def __init__(self, artifacts_dir: str | Path | None = None) -> None:
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else Path(settings.artifacts_dir)

    def _experiment_dir(self, experiment_id: str) -> Path:
        return self.artifacts_dir / "experiments" / experiment_id

    def _load_spec(self, experiment_id: str) -> dict[str, Any]:
        spec = IngestionService.load_from_artifact(experiment_id, self.artifacts_dir)
        if spec is None:
            raise ExperimentNotFound(experiment_id)
        return spec

    def _write(self, experiment_id: str, name: str, payload: dict[str, Any]) -> Path:
        directory = self._experiment_dir(experiment_id)
        directory.mkdir(parents=True, exist_ok=True)
        path = directory / name
        path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        return path

    def _read(self, experiment_id: str, name: str) -> dict[str, Any] | None:
        path = self._experiment_dir(experiment_id) / name
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def run_static(self, experiment_id: str) -> dict[str, Any]:
        spec = self._load_spec(experiment_id)
        context = build_context(spec)
        findings = run_audit(context, "static")
        result = self._build_result(experiment_id, "static", findings)
        self._write(experiment_id, "audit_static.json", result)
        return result

    def run_llm(self, experiment_id: str) -> dict[str, Any]:
        spec = self._load_spec(experiment_id)
        if not settings.groq_api_key:
            # Nothing is persisted, so the report still lists the LLM checks as not run.
            return {"experiment_id": experiment_id, "status": "skipped", "reason": "GROQ_API_KEY is not configured"}
        context = build_context(spec)
        findings = check_ambiguous_claims(context)
        result = self._build_result(experiment_id, "static", findings)
        self._write(experiment_id, "audit_llm.json", result)
        return result

    def run_run_phase(
        self,
        experiment_id: str,
        run_summaries: list[dict[str, Any]] | None = None,
        *,
        execution_id: str | None = None,
    ) -> dict[str, Any]:
        """Audit reproduction results against the paper's claims.

        With explicit `run_summaries`, those are used as-is. Otherwise the summaries are built from the
        runner's execution manifest (`execution_id`, or the latest execution) and the claimed results
        extracted at ingestion.
        """
        spec = self._load_spec(experiment_id)
        execution_limitations: list[dict[str, Any]] = []
        if run_summaries is None:
            summaries, execution_id, execution_limitations = self._summaries_from_execution(spec, execution_id)
        else:
            summaries = [RunSummary(**item) for item in run_summaries]

        context = build_context(spec, run_summaries=summaries)
        findings = run_audit(context, "run")
        result = self._build_result(experiment_id, "run", findings)
        result["execution_id"] = execution_id
        result["run_summaries"] = [s.model_dump() for s in summaries]
        result["claim_verification"] = verify_claims(summaries)
        result["execution_limitations"] = execution_limitations
        self._write(experiment_id, "audit_run.json", result)
        return result

    def _summaries_from_execution(
        self, spec: dict[str, Any], execution_id: str | None
    ) -> tuple[list[RunSummary], str, list[dict[str, Any]]]:
        experiment_id = spec["experiment_id"]
        collector = ResultsCollector(self.artifacts_dir)
        execution_id = execution_id or collector.get_latest_execution_id(experiment_id)
        manifest = collector.load_manifest(experiment_id, execution_id) if execution_id else None
        if manifest is None:
            raise ExecutionNotFound(experiment_id)

        evidence = collector.build_run_evidence(manifest)
        summaries = run_summaries_from_execution(
            spec.get("claimed_results") or [],
            evidence.get("aggregated_metrics") or [],
            execution_id=manifest.execution_id,
            used_assumed_values=self._graph_uses_assumed_values(experiment_id, manifest.graph_version_id),
        )
        return summaries, manifest.execution_id, evidence.get("execution_limitations") or []

    def _graph_uses_assumed_values(self, experiment_id: str, version_id: str) -> bool:
        try:
            from backend.app.graph.service import GraphService
        except ModuleNotFoundError:  # pragma: no cover
            from app.graph.service import GraphService
        try:
            graph = GraphService(artifacts_dir=self.artifacts_dir).get_version(experiment_id, version_id)
        except Exception:
            return False
        if graph is None:
            return False
        return any(
            isinstance(cond, dict) and cond.get("is_assumed")
            for cond in (graph.condition_provenance or {}).values()
        )

    def latest_execution_id(self, experiment_id: str) -> str | None:
        return ResultsCollector(self.artifacts_dir).get_latest_execution_id(experiment_id)

    def get_audit(self, experiment_id: str) -> dict[str, Any] | None:
        static = self._read(experiment_id, "audit_static.json")
        llm = self._read(experiment_id, "audit_llm.json")
        run = self._read(experiment_id, "audit_run.json")
        if static is None and llm is None and run is None:
            return None

        all_findings = []
        for payload in (static, llm, run):
            if payload:
                all_findings.extend(payload.get("findings", []))

        risk = score_findings([Finding(**f) for f in all_findings])
        return {
            "experiment_id": experiment_id,
            "static": static,
            "llm": llm,
            "run": run,
            "claim_verification": (run or {}).get("claim_verification"),
            "findings": all_findings,
            "risk_score": risk.model_dump(),
        }

    @staticmethod
    def _build_result(experiment_id: str, phase: str, findings: list[Finding]) -> dict[str, Any]:
        risk = score_findings(findings)
        return {
            "experiment_id": experiment_id,
            "phase": phase,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "findings": [f.model_dump() for f in findings],
            "risk_score": risk.model_dump(),
        }


__all__ = ["AuditService", "ExperimentNotFound", "ExecutionNotFound"]
