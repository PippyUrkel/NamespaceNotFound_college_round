from __future__ import annotations

from typing import Any

from fastapi import APIRouter, File, Form, HTTPException, UploadFile

from .parser import PDFParser
from .repo_inspector import RepositoryInspector
from .service import IngestionService

router = APIRouter(prefix="/experiments", tags=["experiments"])
service = IngestionService()


@router.get("/{experiment_id}")
def get_experiment(experiment_id: str) -> dict[str, Any]:
    payload = IngestionService.load_from_artifact(experiment_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment_id": experiment_id, "status": payload.get("status"), "artifact_path": payload.get("artifact_path")}


@router.post("/ingest")
async def ingest_experiment(
    file: UploadFile | None = File(default=None),
    repo_url: str | None = Form(default=None),
    branch: str | None = Form(default=None),
    commit_ref: str | None = Form(default=None),
) -> dict[str, Any]:
    if file is None and (repo_url is None or not repo_url.strip()):
        raise HTTPException(status_code=400, detail="Provide either a PDF file or a GitHub repo URL.")

    paper_analysis: dict[str, Any] = {"title": "Untitled paper", "full_text": "", "evidence": []}
    if file is not None:
        if not file.filename or not file.filename.lower().endswith(".pdf"):
            raise HTTPException(status_code=400, detail="Only PDF uploads are supported.")
        file_bytes = await file.read()
        if len(file_bytes) > 25 * 1024 * 1024:
            raise HTTPException(status_code=400, detail="PDF is too large to ingest.")
        paper_analysis = PDFParser.parse_upload(file_bytes, file.filename)

    repo_analysis: dict[str, Any] | None = None
    explicit_repo_url = bool(repo_url and repo_url.strip())
    if explicit_repo_url:
        print(f"[Backend Ingest] Provided repository URL from form: {repo_url}", flush=True)
    elif paper_analysis.get("repo_url"):
        repo_url = paper_analysis.get("repo_url")
        print(f"[Backend Ingest] Using auto-parsed repository URL from research paper: {repo_url}", flush=True)
    else:
        print("[Backend Ingest] No repository URL provided or parsed from research paper.", flush=True)

    normalized_repo_url = repo_url
    if repo_url and repo_url.strip():
        try:
            normalized_repo_url = RepositoryInspector.validate_url(repo_url)
            print(f"[Backend Ingest] Validated repository URL: {normalized_repo_url}", flush=True)
            repo_analysis = RepositoryInspector.inspect(normalized_repo_url, branch=branch, commit_ref=commit_ref)
        except ValueError as exc:
            print(f"[Backend Ingest] Repository validation failed: {exc}", flush=True)
            if explicit_repo_url:
                raise HTTPException(status_code=400, detail=str(exc)) from exc
            normalized_repo_url = None
        except Exception as exc:
            print(f"[Backend Ingest] Repository inspection failed: {exc}", flush=True)
            if explicit_repo_url:
                raise HTTPException(status_code=422, detail=f"Repository inspection failed: {exc}") from exc
            normalized_repo_url = None

    spec = service.build(paper_analysis, repo_analysis, repo_url=normalized_repo_url)
    return {
        "experiment_id": spec["experiment_id"],
        "status": spec["status"],
        "artifact_path": spec["artifact_path"],
        "summary": {
            "title": spec.get("title"),
            "dataset": spec.get("dataset"),
            "feasibility": spec.get("validation", {}).get("feasibility"),
        },
    }


@router.get("/{experiment_id}/spec")
def get_experiment_spec(experiment_id: str) -> dict[str, Any]:
    payload = IngestionService.load_from_artifact(experiment_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return payload


@router.get("/{experiment_id}/evidence")
def get_experiment_evidence(experiment_id: str) -> dict[str, Any]:
    payload = IngestionService.load_from_artifact(experiment_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment_id": experiment_id, "evidence": payload.get("evidence", [])}


@router.get("/{experiment_id}/discrepancies")
def get_experiment_discrepancies(experiment_id: str) -> dict[str, Any]:
    payload = IngestionService.load_from_artifact(experiment_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Experiment not found")
    return {"experiment_id": experiment_id, "discrepancies": payload.get("discrepancies", [])}

