"""Unit and integration tests for SequentialCodeValidator and graph validation endpoints.

Verifies:
1. AST parsing and detection of undefined symbols (specifically `model = MLP().to(device)`).
2. Sequential flow scope accumulation across topologically ordered nodes.
3. Detection of out-of-order / downstream dependencies.
4. Auto-remediation injecting missing device, seed, and model architectures.
5. FastAPI validation and remediation endpoints.
"""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from backend.app.graph.models import DAGEdge, DAGNode, GraphVersion
from backend.app.graph.service import GraphService
from backend.app.graph.validator import SequentialCodeValidator
from backend.app.injestor.service import IngestionService
from backend.app.main import app
from backend.config import settings


@pytest.fixture
def sample_exp_id(tmp_path, monkeypatch) -> str:
    monkeypatch.setattr(settings, "artifacts_dir", str(tmp_path))
    monkeypatch.setattr(settings, "groq_api_key", "")
    service = IngestionService(artifacts_dir=tmp_path)
    paper = {
        "title": "Validation Test Paper",
        "full_text": "Method: CIFAR-10, Adam, lr 0.001, batch 64, epochs 5, seed 42.",
        "hash_sha256": "valsha123",
        "evidence": [],
    }
    repo = {
        "repository_url": "https://github.com/demo/val-project",
        "branch": "main",
        "commit_sha": "valcommit",
        "readme": "Demo",
        "files": {},
        "evidence": [],
    }
    spec = service.build(paper, repo, repo_url="https://github.com/demo/val-project")
    return spec["experiment_id"]


def test_validator_detects_undefined_device_and_mlp_in_snippet() -> None:
    """Verifies that `model = MLP().to(device)` catches both undefined symbols."""
    code_with_missing_device = (
        "import torch\n"
        "model = MLP().to(device)\n"
    )
    node = DAGNode(
        id="model_init",
        name="Model Initialization",
        type="model",
        description="Initializes model",
        code=code_with_missing_device,
    )
    graph = GraphVersion(
        version_id="v1",
        nodes=[node],
        execution_order=["model_init"],
    )

    report = SequentialCodeValidator.validate_graph(graph)
    assert not report.is_valid
    assert report.total_errors >= 1

    issue_symbols = {i.symbol for i in report.issues}
    assert "device" in issue_symbols
    assert "MLP" in issue_symbols

    device_issue = next(i for i in report.issues if i.symbol == "device")
    assert device_issue.severity == "error"
    assert device_issue.category == "undefined_symbol"
    assert "cuda" in (device_issue.suggested_fix or "")


def test_validator_sequential_scope_accumulation() -> None:
    """Verifies that upstream definitions are recognized when run sequentially."""
    node1 = DAGNode(
        id="node_setup",
        name="Setup",
        type="setup",
        description="Setup",
        code=(
            "import torch\n"
            "device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')\n"
            "seed = 42\n"
        ),
    )
    node2 = DAGNode(
        id="node_model",
        name="Model",
        type="model",
        description="Model",
        upstream=["node_setup"],
        code=(
            "import torch.nn as nn\n"
            "class ResearchModel(nn.Module):\n"
            "    def __init__(self): super().__init__(); self.fc = nn.Linear(10, 2)\n"
            "    def forward(self, x): return self.fc(x)\n"
            "model = ResearchModel().to(device)\n"
        ),
    )
    graph = GraphVersion(
        version_id="v1",
        nodes=[node1, node2],
        edges=[DAGEdge(source="node_setup", target="node_model")],
        execution_order=["node_setup", "node_model"],
    )

    report = SequentialCodeValidator.validate_graph(graph)
    assert report.is_valid
    assert report.total_errors == 0


def test_validator_detects_dependency_order_violation() -> None:
    """Verifies that using a symbol defined in a downstream node flags order violation."""
    node1 = DAGNode(
        id="early_node",
        name="Early Node",
        type="eval",
        description="Uses result before computed",
        code="final_score = calculated_accuracy * 100\n",
    )
    node2 = DAGNode(
        id="late_node",
        name="Late Node",
        type="training",
        description="Defines accuracy later",
        code="calculated_accuracy = 0.85\n",
    )
    graph = GraphVersion(
        version_id="v1",
        nodes=[node1, node2],
        execution_order=["early_node", "late_node"],
    )

    report = SequentialCodeValidator.validate_graph(graph)
    assert not report.is_valid
    order_issue = next(
        (i for i in report.issues if i.category == "dependency_order_violation"),
        None,
    )
    assert order_issue is not None
    assert order_issue.symbol == "calculated_accuracy"


def test_validator_auto_remediation_fixes_missing_device_and_mlp() -> None:
    """Verifies that auto-remediation injects device and MLP definitions."""
    broken_code = "model = MLP().to(device)\n"
    node = DAGNode(
        id="model_node",
        name="Model Node",
        type="model",
        description="Broken node",
        code=broken_code,
    )
    graph = GraphVersion(
        version_id="v1",
        nodes=[node],
        execution_order=["model_node"],
    )

    report = SequentialCodeValidator.validate_graph(graph)
    assert not report.is_valid
    assert "model_node" in report.remediated_code_by_node

    fixed_code = report.remediated_code_by_node["model_node"]
    assert "device = torch.device" in fixed_code
    assert "class MLP" in fixed_code

    # Verify remediated code now passes validation
    node.code = fixed_code
    remediated_graph = GraphVersion(
        version_id="v2",
        nodes=[node],
        execution_order=["model_node"],
    )
    new_report = SequentialCodeValidator.validate_graph(remediated_graph)
    assert new_report.is_valid
    assert new_report.total_errors == 0


def test_graph_validation_and_remediation_api_endpoints(sample_exp_id: str) -> None:
    """Verifies GET /validate, POST /validate, and POST /remediate endpoints."""
    client = TestClient(app)

    # 1. Validate endpoint on default generated graph
    val_resp = client.get(f"/experiments/{sample_exp_id}/graph/validate")
    assert val_resp.status_code == 200
    val_data = val_resp.json()
    assert val_data["is_valid"] is True
    assert val_data["total_errors"] == 0

    # 2. Tune graph with a snippet that references undeclared device
    client.post(
        f"/experiments/{sample_exp_id}/graph/tune",
        json={
            "code_updates": {"model_initialization": "model = MLP().to(device)\n"},
            "change_description": "Injected snippet with missing device and MLP",
        },
    )

    # 3. Validate should now detect the issues
    val_resp2 = client.get(f"/experiments/{sample_exp_id}/graph/validate")
    assert val_resp2.status_code == 200
    val_data2 = val_resp2.json()
    assert val_data2["is_valid"] is False
    assert val_data2["total_errors"] > 0
    symbols = [i["symbol"] for i in val_data2["issues"]]
    assert "device" in symbols

    # 4. Call auto-remediate endpoint
    remed_resp = client.post(f"/experiments/{sample_exp_id}/graph/remediate")
    assert remed_resp.status_code == 200
    remed_data = remed_resp.json()
    assert remed_data["remediated"] is True
    assert remed_data["report"]["is_valid"] is True
    assert remed_data["version"]["version_id"] == "v3"


def test_validator_normalizes_semicolon_separated_code() -> None:
    """Verifies that single-line semicolon-separated statements are formatted into multi-line code."""
    from backend.app.graph.validator import normalize_code

    raw_snippet = (
        "import torch,random,numpy as np;torch.manual_seed(seed);"
        "np.random.seed(seed);random.seed(seed);"
        "device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')"
    )
    cleaned = normalize_code(raw_snippet)
    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    assert len(lines) == 5
    assert lines[0] == "import torch,random,numpy as np"
    assert lines[1] == "torch.manual_seed(seed)"
    assert lines[2] == "np.random.seed(seed)"
    assert lines[3] == "random.seed(seed)"
    assert lines[4] == "device=torch.device('cuda' if torch.cuda.is_available() else 'cpu')"

