from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.main import app
from backend.app.injestor.dag import DagBuilder
from backend.app.injestor.parser import PDFParser
from backend.app.injestor.repo_inspector import RepositoryInspector
from backend.app.injestor.service import IngestionService


def test_repository_url_validation_accepts_github_urls() -> None:
    assert RepositoryInspector.validate_url("https://github.com/octocat/hello-world") == "https://github.com/octocat/hello-world"
    assert RepositoryInspector.validate_url("github.com/octocat/hello-world") == "https://github.com/octocat/hello-world"
    assert RepositoryInspector.validate_url("https://github.com/octocat/hello-world.") == "https://github.com/octocat/hello-world"
    assert RepositoryInspector.validate_url("www.github.com/octocat/hello-world") == "https://github.com/octocat/hello-world"
    assert RepositoryInspector.validate_url("git@github.com:octocat/hello-world.git") == "https://github.com/octocat/hello-world"
    assert RepositoryInspector.validate_url("https://facebookresearch.github.io/detectron2") == "https://github.com/facebookresearch/detectron2"
    assert RepositoryInspector.validate_url("https://gitlab.com/user/project") == "https://gitlab.com/user/project"
    assert RepositoryInspector.validate_url("https://github.com\u200b/octocat/hello-world") == "https://github.com/octocat/hello-world"


def test_repository_url_validation_rejects_non_github_urls() -> None:
    with pytest.raises(ValueError):
        RepositoryInspector.validate_url("https://example.com/octocat/hello-world")


def test_pdf_parser_handles_non_pdf_input_without_crashing() -> None:
    result = PDFParser.parse_upload(b"not a real pdf", "notes.txt")
    assert result["hash_sha256"]
    assert "full_text" in result


def test_pdf_parser_extracts_repo_url_from_content() -> None:
    content = b"Paper text. Code available at github.com/octocat/hello-world. Method details..."
    result = PDFParser.parse_upload(content, "paper.pdf")
    assert result["repo_url"] == "https://github.com/octocat/hello-world"


def test_pdf_parser_prefers_normal_text_retrieval_over_ocr() -> None:
    pdf_content = (
        b"%PDF-1.4\n"
        b"1 0 obj << /Type /Catalog /Pages 2 0 R >> endobj\n"
        b"2 0 obj << /Type /Pages /Kids [3 0 R] /Count 1 >> endobj\n"
        b"3 0 obj << /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >> endobj\n"
        b"4 0 obj << /Length 200 >> stream\n"
        b"BT\n/F1 12 Tf\n100 700 Td\n(This is a test research paper on machine learning reproducible experiments using PyTorch and CIFAR-10 dataset with Adam optimizer.) Tj\nET\n"
        b"endstream\nendobj\n"
        b"5 0 obj << /Type /Font /Subtype /Type1 /BaseFont /Helvetica >> endobj\n"
        b"xref\n0 6\n0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000244 00000 n \n0000000495 00000 n \n"
        b"trailer << /Size 6 /Root 1 0 R >>\nstartxref\n574\n%%EOF\n"
    )
    result = PDFParser.parse_upload(pdf_content, "sample.pdf")
    assert result["extraction_method"] == "text_retrieval"
    assert "CIFAR-10" in result["full_text"]


def test_specification_service_builds_json_spec() -> None:
    paper = {
        "title": "Demo research paper",
        "full_text": "Method. Dataset CIFAR-10. Adam optimizer. Learning rate 0.001. Batch size 64. Epochs 10. Seed 42. accuracy.",
        "hash_sha256": "abc123",
        "evidence": [],
    }
    repo = {
        "repository_url": "https://github.com/demo/project",
        "branch": "main",
        "commit_sha": "deadbeef",
        "readme": "This repo trains on CIFAR-10 using Adam.",
        "files": {"README.md": "This repo trains on CIFAR-10 using Adam.", "requirements.txt": "torch\n"},
        "evidence": [],
    }
    spec = IngestionService().build(paper, repo, repo_url="https://github.com/demo/project")
    assert spec["experiment_id"]
    assert spec["validation"]["feasibility"] in {"audit_only", "ready_with_limitations"}
    assert spec["dag"]["nodes"]


def test_dag_is_valid_and_acyclic() -> None:
    dag = DagBuilder.build()
    result = DagBuilder.validate(dag)
    assert result["valid"] is True
    assert len(dag["edges"]) > 0


def test_ingest_endpoint_accepts_repo_url_only() -> None:
    client = TestClient(app)
    response = client.post("/experiments/ingest", data={"repo_url": "https://github.com/octocat/hello-world"})
    assert response.status_code == 200
    payload = response.json()
    assert payload["experiment_id"]
    assert payload["summary"]["title"]
