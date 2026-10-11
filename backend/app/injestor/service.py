from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings
from .comparison import ComparisonService
from .dag import DagBuilder
from .extractor import GroqExtractor
from .feasibility import FeasibilityService
from .parser import PDFParser
from .vector_store import PineconeChunkIndexer


class IngestionService:
    def __init__(self, artifacts_dir: str | Path | None = None) -> None:
        self.artifacts_dir = Path(artifacts_dir) if artifacts_dir else Path(settings.artifacts_dir)

    def build(self, paper_analysis: dict, repo_analysis: dict | None = None, *, repo_url: str | None = None) -> dict:
        extracted = GroqExtractor.extract(paper_analysis, repo_analysis)
        experiment_id = uuid4().hex
        artifact_dir = self.artifacts_dir / "experiments" / experiment_id
        artifact_dir.mkdir(parents=True, exist_ok=True)

        paper_values = {
            "dataset": extracted.get("dataset"),
            "optimizer": extracted.get("optimizer"),
            "learning_rate": extracted.get("learning_rate"),
            "batch_size": extracted.get("batch_size"),
            "epochs": extracted.get("epochs"),
            "seed": extracted.get("seed"),
            "metrics": extracted.get("metrics", []),
            # The rule-based extractor writes this placeholder when the paper names no architecture
            "architecture": None if extracted.get("architecture") == "inferred from paper" else extracted.get("architecture"),
        }
        repo_values = self._repo_values(repo_analysis)
        discrepancies = ComparisonService.compare(paper_values, repo_values)
        feasibility = FeasibilityService.assess(extracted, repo_analysis=repo_analysis)
        dag = DagBuilder.build()
        dag_validation = DagBuilder.validate(dag)
        chunks = PineconeChunkIndexer.build_chunks(paper_analysis, repo_analysis, experiment_id)
        pinecone_status = PineconeChunkIndexer.index_chunks(experiment_id, chunks)

        result = {
            "experiment_id": experiment_id,
            "title": paper_analysis.get("title") or extracted.get("title") or "Untitled paper",
            "repository_url": repo_url,
            "pdf_sha256": paper_analysis.get("hash_sha256"),
            "status": "validated" if dag_validation["valid"] and feasibility["feasibility"] in {"ready", "ready_with_limitations"} else "audit_only",
            "dataset": extracted.get("dataset"),
            "optimizer": extracted.get("optimizer"),
            "learning_rate": extracted.get("learning_rate"),
            "batch_size": extracted.get("batch_size"),
            "epochs": extracted.get("epochs"),
            "seed": extracted.get("seed"),
            "metrics": extracted.get("metrics", []),
            "architecture": extracted.get("architecture"),
            "claimed_results": extracted.get("claimed_results") or [],
            "evidence": (paper_analysis.get("evidence", []) or []) + ((repo_analysis or {}).get("evidence", []) or []),
            "discrepancies": discrepancies,
            "artifact_path": str(artifact_dir / "experiment_spec.json"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "validation": {**feasibility, "dag_valid": dag_validation["valid"]},
            "paper": paper_analysis,
            "repo": repo_analysis,
            "dag": dag,
            "vector_index": pinecone_status,
            "vector_chunks": len(chunks),
        }
        spec_path = artifact_dir / "experiment_spec.json"
        spec_path.write_text(json.dumps(result, indent=2), encoding="utf-8")

        try:
            try:
                from backend.app.graph.service import GraphService
            except ModuleNotFoundError:  # pragma: no cover
                from app.graph.service import GraphService
            GraphService(self.artifacts_dir).generate_graph(experiment_id)
        except Exception as exc:
            print(f"[IngestionService] Graph initialization warning: {exc}", flush=True)

        return result

    @staticmethod
    def _repo_values(repo_analysis: dict | None) -> dict:
        """Configuration values the repository itself states, or None where it states nothing."""
        fields = ("dataset", "optimizer", "learning_rate", "batch_size", "epochs", "seed", "metrics", "architecture")
        if not repo_analysis:
            return dict.fromkeys(fields)
        try:
            from backend.app.graph.parameters import ExperimentConditionResolver
        except ModuleNotFoundError:  # pragma: no cover
            from app.graph.parameters import ExperimentConditionResolver
        # With no paper input, a condition resolved from the repository is exactly the repo's value;
        # anything else was assumed, meaning the repo never stated it.
        report = ExperimentConditionResolver.resolve_conditions({}, {}, repo_analysis)
        values = {}
        for name in fields:
            condition = getattr(report, name)
            values[name] = condition.value if condition.source == "repository" else None
        return values

    @staticmethod
    def load_from_artifact(experiment_id: str, artifacts_dir: str | Path | None = None) -> dict | None:
        base = Path(artifacts_dir) if artifacts_dir else Path(settings.artifacts_dir)
        path = base / "experiments" / experiment_id / "experiment_spec.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["IngestionService"]
