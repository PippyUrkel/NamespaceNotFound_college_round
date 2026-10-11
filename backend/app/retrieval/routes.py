from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException

try:
    from backend.app.injestor.service import IngestionService
except ModuleNotFoundError:  # pragma: no cover
    from app.injestor.service import IngestionService

from .models import RetrievalRequest
from .service import ResearchPaperRetriever

router = APIRouter(prefix="/experiments/{experiment_id}", tags=["retrieval"])


@router.post("/retrieve")
def retrieve_research_chunks(
    experiment_id: str,
    request: RetrievalRequest,
) -> dict[str, Any]:
    spec = IngestionService.load_from_artifact(experiment_id)
    if spec is None:
        raise HTTPException(status_code=404, detail="Experiment not found")

    vector_index = spec.get("vector_index") or {}
    try:
        return ResearchPaperRetriever.retrieve(
            experiment_id=experiment_id,
            question=request.question,
            top_k=request.top_k,
            vector_index=vector_index,
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Retrieval or answer generation failed: {exc}") from exc
