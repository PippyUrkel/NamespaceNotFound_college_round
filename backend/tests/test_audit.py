from __future__ import annotations

import pytest

from backend.app.audit.context import build_context
from backend.app.audit.engine import run_audit
from backend.app.audit.llm_checks import check_ambiguous_claims
from backend.app.audit.models import AuditContext, RunSummary, SpecField
from backend.app.audit.scoring import score as score_findings
from backend.app.audit.service import AuditService, ExperimentNotFound


def _full_fields() -> dict[str, SpecField]:
    return {
        "dataset": SpecField(value="CIFAR-10", source="paper"),
        "optimizer": SpecField(value="Adam", source="paper"),
        "learning_rate": SpecField(value=0.001, source="paper"),
        "batch_size": SpecField(value=64, source="paper"),
        "epochs": SpecField(value=10, source="paper"),
        "seed": SpecField(value=42, source="paper"),
        "metrics": SpecField(value=["accuracy"], source="paper"),
        "architecture": SpecField(value="ResNet-18", source="paper"),
    }


CLEAN_PAPER_TEXT = (
    "We train on CIFAR-10. We report accuracy averaged over 5 runs with seed values "
    "42, 43, 44, 45, 46, mean accuracy 91.2 ± 0.4 (std)."
)


def clean_context(**overrides) -> AuditContext:
    defaults = dict(
        experiment_id="clean-1",
        fields=_full_fields(),
        paper_text=CLEAN_PAPER_TEXT,
        discrepancies=[{"field": "dataset", "status": "match", "paper_value": "CIFAR-10", "repository_value": "CIFAR-10"}],
        has_repo=True,
        repo_files={
            "requirements.txt": "torch==2.1.0\nnumpy==1.26.0\n",
            "train.py": "torch.manual_seed(42)\n",
        },
        repo_dependencies=["torch", "numpy"],
    )
    defaults.update(overrides)
    return AuditContext(**defaults)


def test_clean_context_produces_zero_static_findings() -> None:
    context = clean_context()
    findings = run_audit(context, "static", rule_kwargs={"dataset_unavailable": {"http_get": lambda url: 200}})
    assert findings == []


def test_critical_field_missing_fires_once_per_missing_field() -> None:
    fields = _full_fields()
    fields["architecture"] = SpecField(value=None, source="missing")
    context = clean_context(fields=fields)
    findings = run_audit(context, "static", rule_kwargs={"dataset_unavailable": {"http_get": lambda url: 200}})
    matching = [f for f in findings if f.rule_id == "critical_field_missing:architecture"]
    assert len(matching) == 1
    assert matching[0].status == "confirmed"
    assert matching[0].severity == "high"


def test_missing_seed_fires_when_no_seed_call_in_repo() -> None:
    fields = _full_fields()
    fields["seed"] = SpecField(value=None, source="missing")
    context = clean_context(fields=fields, repo_files={"requirements.txt": "torch==2.1.0\n"})
    findings = run_audit(context, "static")
    assert [f.rule_id for f in findings] == ["missing_seed"]


def test_missing_seed_skips_cleanly_without_repo() -> None:
    fields = _full_fields()
    fields["seed"] = SpecField(value=None, source="missing")
    context = clean_context(fields=fields, has_repo=False, repo_files={})
    findings = [f for f in run_audit(context, "static") if f.rule_id == "missing_seed"]
    assert findings == []


def test_no_variance_reported_fires_without_variance_language() -> None:
    context = clean_context(paper_text="We train on CIFAR-10 and report accuracy of 91.2.")
    findings = [f for f in run_audit(context, "static") if f.rule_id == "no_variance_reported"]
    assert len(findings) == 1


def test_unpinned_dependencies_detected() -> None:
    context = clean_context(repo_files={"requirements.txt": "torch\nnumpy==1.26.0\n"})
    findings = [f for f in run_audit(context, "static") if f.rule_id.startswith("unpinned_dependencies")]
    assert len(findings) == 1
    assert "torch" in findings[0].message


def test_missing_requirements_file_detected() -> None:
    context = clean_context(repo_files={"README.md": "hello"})
    findings = [f for f in run_audit(context, "static") if f.rule_id == "missing_requirements_file"]
    assert len(findings) == 1


def test_paper_vs_code_mismatch_only_on_conflict() -> None:
    context = clean_context(
        discrepancies=[
            {"field": "optimizer", "status": "conflict", "paper_value": "Adam", "repository_value": "SGD"},
            {"field": "dataset", "status": "match", "paper_value": "CIFAR-10", "repository_value": "CIFAR-10"},
        ]
    )
    findings = [f for f in run_audit(context, "static") if f.rule_id.startswith("paper_vs_code_mismatch")]
    assert len(findings) == 1
    assert "optimizer" in findings[0].rule_id


def test_dataset_unavailable_fires_on_unreachable_link() -> None:
    context = clean_context(paper_text="Our dataset is available at https://example.com/data.zip for download.")
    findings = run_audit(
        context, "static", rule_kwargs={"dataset_unavailable": {"http_get": lambda url: 404}}
    )
    matching = [f for f in findings if f.rule_id == "dataset_unavailable"]
    assert len(matching) == 1
    assert "example.com" in matching[0].message


def test_dataset_unavailable_silent_when_no_url_found() -> None:
    context = clean_context(paper_text="We use a dataset described in prior work.")
    findings = [f for f in run_audit(context, "static") if f.rule_id == "dataset_unavailable"]
    assert findings == []


def test_test_set_used_for_tuning_heuristic() -> None:
    context = clean_context(paper_text="We tuned hyperparameters on the test set to maximize accuracy.")
    findings = [f for f in run_audit(context, "static") if f.rule_id == "test_set_used_for_tuning"]
    assert len(findings) == 1
    assert findings[0].status == "possible"


def test_no_code_available_counts_missing_and_assumed_fields() -> None:
    fields = _full_fields()
    fields["seed"] = SpecField(value=None, source="missing")
    context = clean_context(fields=fields, has_repo=False, repo_files={})
    findings = [f for f in run_audit(context, "static") if f.rule_id == "no_code_available"]
    assert len(findings) == 1
    assert "1 spec field(s) are missing" in findings[0].message


def test_no_code_available_skips_when_repo_present() -> None:
    context = clean_context()
    findings = [f for f in run_audit(context, "static") if f.rule_id == "no_code_available"]
    assert findings == []


def test_reproduced_mean_far_from_claim() -> None:
    context = clean_context(
        run_summaries=[
            RunSummary(metric="accuracy", claimed_value=91.2, reproduced_mean=40.0, seeds_run=3, used_assumed_values=True)
        ]
    )
    findings = [f for f in run_audit(context, "run") if f.rule_id.startswith("reproduced_mean_far_from_claim")]
    assert len(findings) == 1
    assert findings[0].severity == "critical"
    assert "assumed configuration values" in findings[0].message


def test_reproduced_mean_within_tolerance_is_silent() -> None:
    context = clean_context(
        run_summaries=[RunSummary(metric="accuracy", claimed_value=91.2, reproduced_mean=90.9, seeds_run=3)]
    )
    findings = run_audit(context, "run")
    assert findings == []


def test_seed_variance_exceeds_claim() -> None:
    context = clean_context(
        run_summaries=[
            RunSummary(metric="accuracy", claimed_improvement=0.5, reproduced_std=2.0, seeds_run=5)
        ]
    )
    findings = [f for f in run_audit(context, "run") if f.rule_id.startswith("seed_variance_exceeds_claim")]
    assert len(findings) == 1


def test_risk_score_weights_confirmed_vs_possible_and_caps_at_100() -> None:
    from backend.app.audit.models import Finding

    findings = [
        Finding(rule_id="a", phase="static", severity="critical", status="confirmed", title="a", message="a"),
        Finding(rule_id="b", phase="static", severity="critical", status="confirmed", title="b", message="b"),
        Finding(rule_id="c", phase="static", severity="critical", status="confirmed", title="c", message="c"),
        Finding(rule_id="d", phase="static", severity="medium", status="possible", title="d", message="d"),
    ]
    result = score_findings(findings)
    assert result.score == 100
    assert result.bucket == "high"
    assert len(result.breakdown) == 4


def test_risk_score_medium_bucket_for_single_confirmed_critical() -> None:
    from backend.app.audit.models import Finding

    result = score_findings(
        [Finding(rule_id="a", phase="static", severity="critical", status="confirmed", title="a", message="a")]
    )
    assert result.score == 40
    assert result.bucket == "medium"


class _FakeGroqClient:
    def __init__(self, payload: str) -> None:
        self._payload = payload

    def chat_completion(self, prompt: str) -> str:
        return self._payload


def test_llm_check_keeps_verified_quote_and_caps_severity() -> None:
    context = clean_context(paper_text="The model achieves strong performance on the benchmark without a baseline comparison.")
    payload = (
        '{"issues": [{"quote": "without a baseline comparison", "section": "Results", '
        '"issue_type": "missing_baseline", "confidence": 0.8, "explanation": "No baseline is reported."}]}'
    )
    findings = check_ambiguous_claims(context, client=_FakeGroqClient(payload))
    assert len(findings) == 1
    assert findings[0].status == "possible"
    assert findings[0].severity == "medium"
    assert findings[0].rule_id == "llm:missing_baseline"


def test_llm_check_drops_fabricated_quote() -> None:
    context = clean_context(paper_text="The model achieves strong performance on the benchmark.")
    payload = (
        '{"issues": [{"quote": "this sentence does not appear anywhere in the paper", '
        '"section": "Results", "issue_type": "leakage_hint", "confidence": 0.9, "explanation": "x"}]}'
    )
    findings = check_ambiguous_claims(context, client=_FakeGroqClient(payload))
    assert findings == []


def test_llm_check_drops_low_confidence_issue() -> None:
    context = clean_context(paper_text="The model achieves strong performance on the benchmark.")
    payload = (
        '{"issues": [{"quote": "strong performance", "section": "Results", '
        '"issue_type": "ambiguous_metric", "confidence": 0.1, "explanation": "x"}]}'
    )
    findings = check_ambiguous_claims(context, client=_FakeGroqClient(payload))
    assert findings == []


def test_llm_check_returns_empty_on_client_error() -> None:
    class _BrokenClient:
        def chat_completion(self, prompt: str) -> str:
            raise RuntimeError("network down")

    context = clean_context()
    assert check_ambiguous_claims(context, client=_BrokenClient()) == []


FULL_SPEC = {
    "experiment_id": "spec-1",
    "title": "Demo paper",
    "repository_url": "https://github.com/demo/project",
    "dataset": "CIFAR-10",
    "optimizer": "Adam",
    "learning_rate": 0.001,
    "batch_size": 64,
    "epochs": 10,
    "seed": 42,
    "metrics": ["accuracy"],
    "architecture": "ResNet-18",
    "evidence": [
        {"source": "paper", "section": "document", "exact_text": CLEAN_PAPER_TEXT},
    ],
    "discrepancies": [
        {"field": "dataset", "status": "match", "paper_value": "CIFAR-10", "repository_value": "CIFAR-10"}
    ],
    "repo": {
        "files": {
            "requirements.txt": "torch==2.1.0\nnumpy==1.26.0\n",
            "train.py": "torch.manual_seed(42)\n",
        },
        "dependencies": ["torch", "numpy"],
    },
}


def test_build_context_from_full_spec_produces_zero_static_findings() -> None:
    context = build_context(FULL_SPEC)
    findings = run_audit(context, "static", rule_kwargs={"dataset_unavailable": {"http_get": lambda url: 200}})
    assert findings == []


def test_build_context_reconstructs_paper_text_from_evidence_when_absent() -> None:
    context = build_context(FULL_SPEC, paper_text="")
    assert "CIFAR-10" in context.paper_text


def test_audit_service_persists_and_merges_static_and_run_results(tmp_path) -> None:
    from backend.app.injestor.service import IngestionService

    ingestion = IngestionService(artifacts_dir=tmp_path)
    spec = ingestion.build(
        {
            "title": "Demo research paper",
            "full_text": CLEAN_PAPER_TEXT,
            "hash_sha256": "abc123",
            "evidence": [],
        },
        {
            "repository_url": "https://github.com/demo/project",
            "branch": "main",
            "commit_sha": "deadbeef",
            "readme": "CIFAR-10 with Adam.",
            "files": {"requirements.txt": "torch==2.1.0\n"},
            "evidence": [],
        },
        repo_url="https://github.com/demo/project",
    )
    experiment_id = spec["experiment_id"]

    audit_service = AuditService(artifacts_dir=tmp_path)
    static_result = audit_service.run_static(experiment_id)
    assert static_result["phase"] == "static"
    assert "risk_score" in static_result

    run_result = audit_service.run_run_phase(
        experiment_id,
        [{"metric": "accuracy", "claimed_value": 91.2, "reproduced_mean": 60.0, "seeds_run": 3}],
    )
    assert any(f["rule_id"].startswith("reproduced_mean_far_from_claim") for f in run_result["findings"])

    merged = audit_service.get_audit(experiment_id)
    assert merged is not None
    assert merged["static"] is not None
    assert merged["run"] is not None
    assert len(merged["findings"]) == len(static_result["findings"]) + len(run_result["findings"])


def test_audit_service_raises_for_unknown_experiment(tmp_path) -> None:
    audit_service = AuditService(artifacts_dir=tmp_path)
    with pytest.raises(ExperimentNotFound):
        audit_service.run_static("does-not-exist")


def test_audit_routes_end_to_end(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from backend.app.audit import routes as audit_routes
    from backend.app.injestor.service import IngestionService
    from backend.app.main import app

    monkeypatch.setattr(audit_routes, "service", AuditService(artifacts_dir=tmp_path))

    ingestion = IngestionService(artifacts_dir=tmp_path)
    spec = ingestion.build(
        {"title": "Demo paper", "full_text": CLEAN_PAPER_TEXT, "hash_sha256": "x", "evidence": []},
        None,
        repo_url=None,
    )
    experiment_id = spec["experiment_id"]

    client = TestClient(app)
    response = client.post(f"/experiments/{experiment_id}/audit/static")
    assert response.status_code == 200
    assert "risk_score" in response.json()

    response = client.get(f"/experiments/{experiment_id}/audit")
    assert response.status_code == 200

    response = client.get("/experiments/missing-id/audit")
    assert response.status_code == 404
