from __future__ import annotations

import json
import pytest
from fastapi.testclient import TestClient

from backend.app.graph.generator import GraphCodeGenerator
from backend.app.graph.models import TuneParameterRequest
from backend.app.graph.service import GraphService
from backend.app.injestor.service import IngestionService
from backend.app.main import app
from backend.config import settings


@pytest.fixture
def sample_experiment(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    monkeypatch.setattr(settings, "groq_api_key", "")
    service = IngestionService(artifacts_dir=tmp_path)
    paper = {
        "title": "Reproducible Transformers Paper",
        "full_text": "Method: Dataset CIFAR-10. Adam optimizer. Learning rate 0.001. Batch size 64. Epochs 10. Seed 42. Accuracy 85.5%.",
        "hash_sha256": "123abc456",
        "evidence": [],
    }
    repo = {
        "repository_url": "https://github.com/demo/reproducible-project",
        "branch": "main",
        "commit_sha": "c0ffee",
        "readme": "Dataset: CIFAR-10\nTraining command: python train.py --seed 42",
        "files": {
            "train.py": "def train():\n    for epoch in range(10):\n        optimizer.step()\n",
            "model.py": "class CNNClassifier(nn.Module):\n    pass\n",
        },
        "evidence": [],
    }
    spec = service.build(paper, repo, repo_url="https://github.com/demo/reproducible-project")
    return spec["experiment_id"]


def test_graph_code_generator_creates_all_six_nodes_with_dependencies() -> None:
    spec = {
        "title": "Sample Paper",
        "dataset": "CIFAR-10",
        "optimizer": "Adam",
        "learning_rate": 0.001,
        "batch_size": 64,
        "epochs": 10,
        "seed": 42,
        "architecture": "CNNClassifier",
        "metrics": ["accuracy"],
    }
    nodes, edges = GraphCodeGenerator.generate_dag(spec)
    node_ids = [n.id for n in nodes]
    assert len(nodes) == 6
    assert node_ids == [
        "setup_environment",
        "data_pipeline",
        "model_initialization",
        "training_pipeline",
        "evaluation_pipeline",
        "claim_verification",
    ]

    setup_node = next(n for n in nodes if n.id == "setup_environment")
    assert setup_node.upstream == []
    assert setup_node.parameters["seed"] == 42
    assert "42" in setup_node.code

    training_node = next(n for n in nodes if n.id == "training_pipeline")
    assert "data_pipeline" in training_node.upstream
    assert "model_initialization" in training_node.upstream
    assert training_node.parameters["epochs"] == 10
    assert "10" in training_node.code


def test_get_graph_endpoint_returns_ready_dag_structure(sample_experiment: str) -> None:
    client = TestClient(app)
    response = client.get(f"/experiments/{sample_experiment}/graph")
    assert response.status_code == 200
    data = response.json()
    assert data["version_id"] == "v1"
    assert len(data["nodes"]) == 6
    assert len(data["edges"]) >= 6
    assert data["execution_order"][0] == "setup_environment"
    assert data["graph_hash"]


def test_graph_fine_tuning_creates_immutable_new_version(sample_experiment: str) -> None:
    client = TestClient(app)

    # Fine tune parameters
    tune_payload = {
        "parameters": {"seed": 999, "learning_rate": 0.0001, "epochs": 25},
        "change_description": "Updated seed to 999, lowered lr and increased epochs",
    }
    tune_resp = client.post(f"/experiments/{sample_experiment}/graph/tune", json=tune_payload)
    assert tune_resp.status_code == 200
    v2_data = tune_resp.json()
    assert v2_data["version_id"] == "v2"
    assert v2_data["parent_version"] == "v1"
    assert v2_data["parameters_summary"]["seed"] == 999
    assert v2_data["parameters_summary"]["learning_rate"] == 0.0001

    setup_node = next(n for n in v2_data["nodes"] if n["id"] == "setup_environment")
    assert "999" in setup_node["code"]

    training_node = next(n for n in v2_data["nodes"] if n["id"] == "training_pipeline")
    assert "0.0001" in training_node["code"]
    assert "25" in training_node["code"]

    # Check that v1 is preserved and untouched
    v1_resp = client.get(f"/experiments/{sample_experiment}/graph/versions/v1")
    assert v1_resp.status_code == 200
    v1_data = v1_resp.json()
    assert v1_data["version_id"] == "v1"
    v1_setup = next(n for n in v1_data["nodes"] if n["id"] == "setup_environment")
    assert v1_setup["parameters"]["seed"] == 42


def test_graph_versions_and_diff_endpoints(sample_experiment: str) -> None:
    client = TestClient(app)

    # 1. First tune
    tune_resp = client.post(
        f"/experiments/{sample_experiment}/graph/tune",
        json={"parameters": {"seed": 777, "batch_size": 128}, "change_description": "Tune batch and seed"},
    )
    assert tune_resp.status_code == 200

    # 2. List versions
    versions_resp = client.get(f"/experiments/{sample_experiment}/graph/versions")
    assert versions_resp.status_code == 200
    versions = versions_resp.json()
    assert len(versions) == 2
    assert versions[0]["version_id"] == "v1"
    assert versions[1]["version_id"] == "v2"

    # 3. Check diff
    diff_resp = client.get(f"/experiments/{sample_experiment}/graph/diff?from_version=v1&to_version=v2")
    assert diff_resp.status_code == 200
    diff = diff_resp.json()
    assert "seed" in diff["parameter_changes"]
    assert diff["parameter_changes"]["seed"]["new"] == 777
    assert "batch_size" in diff["parameter_changes"]
    assert diff["parameter_changes"]["batch_size"]["new"] == 128
    assert len(diff["modified_nodes"]) >= 1


def test_graph_handles_nonexistent_experiment() -> None:
    client = TestClient(app)
    response = client.get("/experiments/nonexistent_id/graph")
    assert response.status_code == 404


def test_exact_parameter_conditions_mimicked_and_reconciled(sample_experiment: str) -> None:
    client = TestClient(app)
    response = client.get(f"/experiments/{sample_experiment}/graph")
    assert response.status_code == 200
    data = response.json()

    # 1. Condition Provenance in GraphVersion
    cond_prov = data["condition_provenance"]
    assert "seed" in cond_prov
    assert cond_prov["seed"]["value"] == 42
    assert cond_prov["seed"]["source"] == "reconciled"
    assert cond_prov["seed"]["is_assumed"] is False
    assert cond_prov["seed"]["confidence"] == 1.0

    assert cond_prov["dataset"]["value"] == "CIFAR-10"
    assert cond_prov["dataset"]["source"] == "reconciled"

    # 2. Setup Node parameter & determinism assertions
    setup_node = next(n for n in data["nodes"] if n["id"] == "setup_environment")
    assert setup_node["parameters"]["seed"] == 42
    assert setup_node["parameters"]["seed_source"] == "reconciled"
    assert setup_node["parameters"]["seed_is_assumed"] is False
    assert 'PYTHONHASHSEED' in setup_node["code"]
    assert 'torch.manual_seed(seed)' in setup_node["code"]
    assert 'np.random.seed(seed)' in setup_node["code"]
    assert 'torch.backends.cudnn.deterministic = True' in setup_node["code"]

    # 3. Data Pipeline Generator assertions
    data_node = next(n for n in data["nodes"] if n["id"] == "data_pipeline")
    assert "torch.Generator()" in data_node["code"]
    assert "generator=g" in data_node["code"]

    # 4. Claim Verification audit report
    claim_node = next(n for n in data["nodes"] if n["id"] == "claim_verification")
    assert claim_node["parameters"]["seed_audit_source"] == "reconciled"
    assert claim_node["parameters"]["is_assumed_seed"] is False
    assert "seed_audit" in claim_node["code"]


def test_assumed_seed_flagged_when_missing_from_paper_and_repo(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    monkeypatch.setattr(settings, "groq_api_key", "")
    service = IngestionService(artifacts_dir=tmp_path)
    paper = {
        "title": "Paper Without Stated Seed",
        "full_text": "Method: Trained with CIFAR-10. Adam optimizer. Learning rate 0.001. Batch size 64. Epochs 10.",
        "hash_sha256": "456def",
        "evidence": [],
    }
    repo = {
        "repository_url": "https://github.com/demo/no-seed-repo",
        "branch": "main",
        "commit_sha": "f00baa",
        "readme": "Run python train.py",
        "files": {"train.py": "def train(): pass\n"},
        "evidence": [],
    }
    spec = service.build(paper, repo, repo_url="https://github.com/demo/no-seed-repo")
    exp_id = spec["experiment_id"]

    client = TestClient(app)
    response = client.get(f"/experiments/{exp_id}/graph")
    assert response.status_code == 200
    data = response.json()

    seed_prov = data["condition_provenance"]["seed"]
    assert seed_prov["source"] == "assumed"
    assert seed_prov["value"] == 42
    assert seed_prov["is_assumed"] is True

    claim_node = next(n for n in data["nodes"] if n["id"] == "claim_verification")
    assert claim_node["parameters"]["is_assumed_seed"] is True
    assert "audit recommended" in claim_node["code"]


def test_discrepancy_flagged_when_paper_and_repo_disagree(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    monkeypatch.setattr(settings, "groq_api_key", "")
    service = IngestionService(artifacts_dir=tmp_path)
    paper = {
        "title": "Discrepancy Paper",
        "full_text": "Method: Seed 42. Dataset CIFAR-10.",
        "hash_sha256": "789ghi",
        "evidence": [],
    }
    repo = {
        "repository_url": "https://github.com/demo/discrepant-repo",
        "branch": "main",
        "commit_sha": "badc0de",
        "readme": "python train.py --seed 1337",
        "files": {"train.py": "torch.manual_seed(1337)\n"},
        "evidence": [],
    }
    spec = service.build(paper, repo, repo_url="https://github.com/demo/discrepant-repo")
    exp_id = spec["experiment_id"]

    client = TestClient(app)
    response = client.get(f"/experiments/{exp_id}/graph")
    assert response.status_code == 200
    data = response.json()

    seed_prov = data["condition_provenance"]["seed"]
    assert seed_prov["source"] == "paper"
    assert seed_prov["value"] == 42
    assert seed_prov["discrepancy"] is not None
    assert "1337" in seed_prov["discrepancy"]


def test_tuning_updates_condition_provenance_to_tuned(sample_experiment: str) -> None:
    client = TestClient(app)
    tune_resp = client.post(
        f"/experiments/{sample_experiment}/graph/tune",
        json={"parameters": {"seed": 1234}, "change_description": "Auditor seed variance test"},
    )
    assert tune_resp.status_code == 200
    v2_data = tune_resp.json()

    seed_prov = v2_data["condition_provenance"]["seed"]
    assert seed_prov["value"] == 1234
    assert seed_prov["source"] == "tuned"
    assert seed_prov["is_assumed"] is False

    # Check untouched condition provenance remains reconciled
    dataset_prov = v2_data["condition_provenance"]["dataset"]
    assert dataset_prov["source"] == "reconciled"


def test_groq_llm_code_synthesis_path(monkeypatch) -> None:
    class MockChoice:
        message = type("Msg", (), {
            "content": json.dumps({
                "setup_environment": "import torch\nseed = 42\ntorch.manual_seed(seed)",
                "data_pipeline": "import torch\ntrain_loader = None",
                "model_initialization": "import torch\nmodel = None",
                "training_pipeline": "import torch\n# training loop",
                "evaluation_pipeline": "import torch\neval_results = {'accuracy': 90.0}",
                "claim_verification": "print('verified')",
            })
        })()

    class MockCompletion:
        choices = [MockChoice()]

    class MockCompletions:
        def create(self, **kwargs):
            return MockCompletion()

    class MockChat:
        completions = MockCompletions()

    class MockGroq:
        def __init__(self, api_key):
            self.chat = MockChat()

    monkeypatch.setattr(settings, "groq_api_key", "mock_key")
    import sys
    mock_module = type(sys)("groq")
    mock_module.Groq = MockGroq
    monkeypatch.setitem(sys.modules, "groq", mock_module)

    spec = {
        "title": "LLM Synthesis Paper",
        "dataset": "CIFAR-10",
        "seed": 42,
    }
    nodes, edges = GraphCodeGenerator.generate_dag(spec)
    assert len(nodes) == 6
    setup_node = next(n for n in nodes if n.id == "setup_environment")
    assert setup_node.provenance.source in {"paper", "paper_llm_generated", "reconciled"}
    assert "torch.manual_seed(seed)" in setup_node.code

