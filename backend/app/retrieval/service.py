from __future__ import annotations

from typing import Any

from groq import Groq
from sentence_transformers import SentenceTransformer

try:
    from pinecone import Pinecone
except ImportError:  # pragma: no cover
    Pinecone = None

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings


class ResearchPaperRetriever:
    @staticmethod
    def retrieve(
        *,
        experiment_id: str,
        question: str,
        top_k: int,
        vector_index: dict[str, Any],
    ) -> dict[str, Any]:
        namespace = vector_index.get("namespace")
        if not namespace:
            raise ValueError("This experiment has no paper namespace. Re-ingest the paper before retrieving chunks.")
        if vector_index.get("status") != "indexed":
            reason = vector_index.get("reason") or "No vectors were indexed for this experiment."
            raise RuntimeError(reason)
        if not settings.pinecone_api_key or Pinecone is None:
            raise RuntimeError("Pinecone is not configured on the server.")

        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        embedding = model.encode(question, normalize_embeddings=True).tolist()
        client = Pinecone(api_key=settings.pinecone_api_key)
        index = client.Index(settings.pinecone_index)
        response = index.query(
            vector=embedding,
            top_k=top_k,
            include_metadata=True,
            namespace=namespace,
            filter={
                "experiment_id": {"$eq": experiment_id},
                "source_type": {"$eq": "paper"},
            },
        )
        matches = []
        for match in response.matches:
            metadata = dict(match.metadata or {})
            matches.append({
                "id": match.id,
                "score": match.score,
                "text": metadata.get("chunk_text", ""),
                "source_type": metadata.get("source_type"),
                "metadata": {
                    key: value
                    for key, value in metadata.items()
                    if key != "chunk_text"
                },
            })
        answer = ResearchPaperRetriever._answer_question(question, matches)
        return {
            "experiment_id": experiment_id,
            "namespace": namespace,
            "question": question,
            "answer": answer,
            "matches": matches,
        }

    @staticmethod
    def _answer_question(question: str, matches: list[dict[str, Any]]) -> str:
        if not matches:
            return "I couldn't find relevant passages in this paper to answer the question."
        if not settings.groq_api_key:
            raise RuntimeError("Groq is not configured on the server.")

        evidence = "\n\n".join(
            f"[{i}] {match['text']}" for i, match in enumerate(matches, start=1)
        )
        response = Groq(api_key=settings.groq_api_key).chat.completions.create(
            model=settings.groq_model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Answer questions using the supplied research-paper passages. First state what "
                        "the paper explicitly reports, citing passage numbers like [1]. Do not present "
                        "an inference as a fact reported by the paper. When the passages do not specify "
                        "the answer, infer the most plausible answer from the paper's described models, "
                        "task, data, and methods, and use relevant established general knowledge to make "
                        "the answer useful. Clearly label it as an inference, explain the key assumption, "
                        "and state when it is uncertain. Match recommendations to the method: for example, "
                        "Adam can be a reasonable optimizer for a neural network, but is not an optimizer "
                        "for a decision tree; for classical estimators, discuss a compatible estimator "
                        "or training procedure instead. Do not invent paper-specific values, cite general "
                        "knowledge as if it came from the passages, or claim to have performed a live "
                        "web search. Keep the answer direct, distinguish 'Reported by the paper' from "
                        "'Inference based on the paper and general knowledge', and cite supporting paper "
                        "passages like [1] where applicable. If the evidence is too weak to make a useful "
                        "inference, say what assumption or detail is missing."
                    ),
                },
                {
                    "role": "user",
                    "content": f"Question: {question}\n\nPaper passages:\n{evidence}",
                },
            ],
            temperature=0.0,
        )
        answer = response.choices[0].message.content
        if not answer or not answer.strip():
            raise RuntimeError("Groq returned an empty answer.")
        return answer.strip()
