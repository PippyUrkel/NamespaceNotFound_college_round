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
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.service import IngestionService

from .context import build_context
from .engine import run_audit
from .llm_checks import check_ambiguous_claims
from .models import Finding, RunSummary
from .scoring import score as score_findings

class ExperimentNotFound(Exception):
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
        context = build_context(spec)
        findings = check_ambiguous_claims(context)
        result = self._build_result(experiment_id, "static", findings)
        self._write(experiment_id, "audit_llm.json", result)
        return result

    def run_run_phase(self, experiment_id: str, run_summaries: list[dict[str, Any]]) -> dict[str, Any]:
        spec = self._load_spec(experiment_id)
        context = build_context(spec, run_summaries=[RunSummary(**item) for item in run_summaries])
        findings = run_audit(context, "run")
        result = self._build_result(experiment_id, "run", findings)
        self._write(experiment_id, "audit_run.json", result)
        return result

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


__all__ = ["AuditService", "ExperimentNotFound"]
