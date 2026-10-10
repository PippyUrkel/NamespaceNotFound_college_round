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
            "title": paper_analysis.get("title") or extracted.get("title"),
            "dataset": extracted.get("dataset"),
            "optimizer": extracted.get("optimizer"),
            "learning_rate": extracted.get("learning_rate"),
            "batch_size": extracted.get("batch_size"),
            "epochs": extracted.get("epochs"),
            "seed": extracted.get("seed"),
            "metrics": extracted.get("metrics", []),
            "architecture": extracted.get("architecture"),
        }
        repo_values = {
            "repository_url": repo_url,
            "dataset": (repo_analysis or {}).get("files", {}).get("README.md") or (repo_analysis or {}).get("readme"),
            "optimizer": None,
            "learning_rate": None,
            "batch_size": None,
            "epochs": None,
            "seed": None,
            "metrics": [],
            "architecture": None,
        }
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
    def load_from_artifact(experiment_id: str, artifacts_dir: str | Path | None = None) -> dict | None:
        base = Path(artifacts_dir) if artifacts_dir else Path(settings.artifacts_dir)
        path = base / "experiments" / experiment_id / "experiment_spec.json"
        if not path.exists():
            return None
        return json.loads(path.read_text(encoding="utf-8"))


__all__ = ["IngestionService"]
