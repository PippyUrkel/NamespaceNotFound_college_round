from __future__ import annotations

import json
from pathlib import Path
from typing import Any

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings

try:
    from backend.app.audit.service import AuditService, ExperimentNotFound
    from backend.app.injestor.service import IngestionService
except ModuleNotFoundError:  # pragma: no cover
    from app.audit.service import AuditService, ExperimentNotFound
    from app.injestor.service import IngestionService

from .builder import build_report, render_markdown

REPORT_JSON = "report.json"
REPORT_MD = "report.md"


class ReportService:
    def __init__(self, artifacts_dir: str | Path | None = None, audit_service: AuditService | None = None) -> None:
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else Path(settings.artifacts_dir)
        self.audit_service = audit_service or AuditService(artifacts_dir=self.artifacts_dir)

    def _experiment_dir(self, experiment_id: str) -> Path:
        return self.artifacts_dir / "experiments" / experiment_id

    def generate(self, experiment_id: str) -> dict[str, Any]:
        spec = IngestionService.load_from_artifact(experiment_id, self.artifacts_dir)
        if spec is None:
            raise ExperimentNotFound(experiment_id)
        audit = self.audit_service.get_audit(experiment_id)
        if audit is None:
            self.audit_service.run_static(experiment_id)
            audit = self.audit_service.get_audit(experiment_id)

        report = build_report(spec, audit)
        directory = self._experiment_dir(experiment_id)
        directory.mkdir(parents=True, exist_ok=True)
        (directory / REPORT_JSON).write_text(json.dumps(report, indent=2), encoding="utf-8")
        (directory / REPORT_MD).write_text(render_markdown(report), encoding="utf-8")
        return report

    def get(self, experiment_id: str) -> dict[str, Any] | None:
        path = self._experiment_dir(experiment_id) / REPORT_JSON
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))

    def get_markdown(self, experiment_id: str) -> str | None:
        path = self._experiment_dir(experiment_id) / REPORT_MD
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8")


__all__ = ["ReportService", "ExperimentNotFound"]
