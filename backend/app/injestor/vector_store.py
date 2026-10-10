from __future__ import annotations

import hashlib
import re
from typing import Any

from sentence_transformers import SentenceTransformer

try:
    from pinecone import Pinecone
except Exception:  # pragma: no cover
    Pinecone = None

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings


class PineconeChunkIndexer:
    @staticmethod
    def chunk_texts(text: str, *, source: str, experiment_id: str) -> list[dict[str, Any]]:
        cleaned = re.sub(r"\s+", " ", text or "").strip()
        if not cleaned:
            return []
        chunks: list[dict[str, Any]] = []
        segment_size = 500
        overlap = 80
        for start in range(0, len(cleaned), segment_size - overlap):
            segment = cleaned[start:start + segment_size].strip()
            if len(segment) < 30:
                continue
            chunk_id = hashlib.sha256(f"{experiment_id}:{source}:{start}:{segment}".encode("utf-8")).hexdigest()[:32]
            chunks.append({
                "id": chunk_id,
                "text": segment,
                "metadata": {
                    "experiment_id": experiment_id,
                    "source_type": source,
                    "chunk_type": "text",
                    "evidence_id": chunk_id,
                },
            })
        return chunks

    @staticmethod
    def build_chunks(paper_analysis: dict[str, Any], repo_analysis: dict[str, Any] | None, experiment_id: str) -> list[dict[str, Any]]:
        chunks: list[dict[str, Any]] = []
        paper_text = str(paper_analysis.get("full_text") or "")
        if paper_text:
            chunks.extend(PineconeChunkIndexer.chunk_texts(paper_text, source="paper", experiment_id=experiment_id))

        if repo_analysis:
            for file_name, content in (repo_analysis.get("files") or {}).items():
                if not isinstance(content, str):
                    continue
                chunks.extend(PineconeChunkIndexer.chunk_texts(content, source=file_name, experiment_id=experiment_id))
            readme = repo_analysis.get("readme")
            if readme:
                chunks.extend(PineconeChunkIndexer.chunk_texts(readme, source="readme", experiment_id=experiment_id))
        return chunks

    @staticmethod
    def index_chunks(experiment_id: str, chunks: list[dict[str, Any]]) -> dict[str, Any]:
        if not chunks:
            return {"status": "skipped", "count": 0, "index_name": settings.pinecone_index}
        api_key = settings.pinecone_api_key or None
        if not api_key or Pinecone is None:
            return {"status": "skipped", "count": 0, "index_name": settings.pinecone_index, "reason": "Pinecone is not configured"}

        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        client = Pinecone(api_key=api_key)
        try:
            client.create_index(
                name=settings.pinecone_index,
                dimension=384,
                metric="cosine",
                spec={"serverless": {"cloud": settings.pinecone_cloud or "aws", "region": settings.pinecone_region or "us-east-1"}},
            )
        except Exception:
            pass

        index = client.Index(settings.pinecone_index)
        vectors = []
        for chunk in chunks:
            text = str(chunk["text"])
            embedding = model.encode(text, normalize_embeddings=True).tolist()
            metadata = dict(chunk["metadata"])
            metadata["chunk_text"] = text
            vectors.append({
                "id": chunk["id"],
                "values": embedding,
                "metadata": metadata,
            })
        if vectors:
            index.upsert(vectors=vectors)
        return {"status": "indexed", "count": len(vectors), "index_name": settings.pinecone_index}
