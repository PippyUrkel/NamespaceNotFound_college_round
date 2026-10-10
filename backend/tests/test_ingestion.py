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
