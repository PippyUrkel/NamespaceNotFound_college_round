from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from backend.app.injestor.service import IngestionService
from backend.app.injestor import vector_store
from backend.app.main import app
from backend.app.retrieval.models import RetrievalRequest
from backend.app.retrieval import service as retrieval_service


def test_retrieval_request_has_no_prefilled_question_and_defaults_to_eight_results() -> None:
    request = RetrievalRequest(question="A user-provided question")

    assert request.top_k == 8
    assert "question" in RetrievalRequest.model_fields
    assert RetrievalRequest.model_fields["question"].is_required()
    assert "source_type" not in RetrievalRequest.model_fields


def test_paper_namespace_is_stable_and_paper_specific() -> None:
    first = vector_store.PineconeChunkIndexer.namespace_for_paper("paper-hash", "experiment-1")
    same_paper = vector_store.PineconeChunkIndexer.namespace_for_paper("paper-hash", "experiment-2")
    another_paper = vector_store.PineconeChunkIndexer.namespace_for_paper("other-hash", "experiment-1")

    assert first == same_paper
    assert first != another_paper


def test_index_chunks_upserts_into_given_namespace(monkeypatch) -> None:
    captured: dict = {}

    class FakeModel:
        def __init__(self, _name: str) -> None:
            pass

        def encode(self, _text: str, normalize_embeddings: bool) -> SimpleNamespace:
            assert normalize_embeddings is True
            return SimpleNamespace(tolist=lambda: [0.1, 0.2])

    class FakeIndex:
        def upsert(self, *, vectors: list[dict], namespace: str) -> None:
            captured["vectors"] = vectors
            captured["namespace"] = namespace

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"

        def create_index(self, **_kwargs) -> None:
            pass

        def Index(self, _index_name: str) -> FakeIndex:
            return FakeIndex()

    monkeypatch.setattr(vector_store.settings, "pinecone_api_key", "test-key")
    monkeypatch.setattr(vector_store, "Pinecone", FakeClient)
    monkeypatch.setattr(vector_store, "SentenceTransformer", FakeModel)
    namespace = "paper-123"

    result = vector_store.PineconeChunkIndexer.index_chunks(
        "experiment-1",
        [{"id": "chunk-1", "text": "Research text", "metadata": {"experiment_id": "experiment-1"}}],
        namespace=namespace,
    )

    assert result["namespace"] == namespace
    assert result["status"] == "indexed"
    assert captured["namespace"] == namespace


def test_retrieval_queries_paper_namespace_and_returns_text(monkeypatch) -> None:
    captured: dict = {}

    class FakeModel:
        def __init__(self, _name: str) -> None:
            pass

        def encode(self, question: str, normalize_embeddings: bool) -> SimpleNamespace:
            assert question == "How was it trained?"
            assert normalize_embeddings is True
            return SimpleNamespace(tolist=lambda: [0.4, 0.5])

    class FakeIndex:
        def query(self, **kwargs) -> SimpleNamespace:
            captured.update(kwargs)
            match = SimpleNamespace(
                id="chunk-1",
                score=0.91,
                metadata={
                    "chunk_text": "The model was trained for ten epochs.",
                    "source_type": "paper",
                    "experiment_id": "experiment-1",
                },
            )
            return SimpleNamespace(matches=[match])

    class FakeGroq:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"
            self.chat = SimpleNamespace(
                completions=SimpleNamespace(
                    create=lambda **kwargs: (
                        captured.update({"groq_request": kwargs})
                        or SimpleNamespace(
                            choices=[
                                SimpleNamespace(
                                    message=SimpleNamespace(content="It was trained for ten epochs. [1]")
                                )
                            ]
                        )
                    )
                )
            )

    class FakeClient:
        def __init__(self, *, api_key: str) -> None:
            assert api_key == "test-key"

        def Index(self, _index_name: str) -> FakeIndex:
            return FakeIndex()

    monkeypatch.setattr(retrieval_service.settings, "pinecone_api_key", "test-key")
    monkeypatch.setattr(retrieval_service.settings, "groq_api_key", "test-key")
    monkeypatch.setattr(retrieval_service, "Pinecone", FakeClient)
    monkeypatch.setattr(retrieval_service, "SentenceTransformer", FakeModel)
    monkeypatch.setattr(retrieval_service, "Groq", FakeGroq)

    result = retrieval_service.ResearchPaperRetriever.retrieve(
        experiment_id="experiment-1",
        question="How was it trained?",
        top_k=3,
        vector_index={"status": "indexed", "namespace": "paper-123"},
    )

    assert captured["namespace"] == "paper-123"
    assert captured["top_k"] == 3
    assert captured["filter"] == {
        "experiment_id": {"$eq": "experiment-1"},
        "source_type": {"$eq": "paper"},
    }
    assert result["matches"][0]["text"] == "The model was trained for ten epochs."
    assert result["answer"] == "It was trained for ten epochs. [1]"
    assert captured["groq_request"]["temperature"] == 0.0
    system_prompt = captured["groq_request"]["messages"][0]["content"]
    assert "Inference based on the paper and general knowledge" in system_prompt
    assert "infer the most plausible answer" in system_prompt
    assert "Adam can be a reasonable optimizer for a neural network" in system_prompt
    assert "not an optimizer for a decision tree" in system_prompt


def test_retrieval_endpoint_loads_experiment_namespace(monkeypatch) -> None:
    monkeypatch.setattr(
        IngestionService,
        "load_from_artifact",
        staticmethod(lambda _experiment_id: {"vector_index": {"status": "indexed", "namespace": "paper-123"}}),
    )
    monkeypatch.setattr(
        retrieval_service.ResearchPaperRetriever,
        "retrieve",
        staticmethod(lambda **kwargs: {
            "experiment_id": kwargs["experiment_id"],
            "answer": "It used the CIFAR-10 dataset. [1]",
            "matches": [],
        }),
    )

    response = TestClient(app).post(
        "/experiments/experiment-1/retrieve",
        json={"question": "What dataset was used?"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "experiment_id": "experiment-1",
        "answer": "It used the CIFAR-10 dataset. [1]",
        "matches": [],
    }


def test_empty_retrieval_returns_clear_answer_without_groq(monkeypatch) -> None:
    monkeypatch.setattr(retrieval_service.settings, "groq_api_key", "test-key")

    answer = retrieval_service.ResearchPaperRetriever._answer_question("What batch size?", [])

    assert answer == "I couldn't find relevant passages in this paper to answer the question."
