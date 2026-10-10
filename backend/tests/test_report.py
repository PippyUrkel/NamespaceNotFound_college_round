from __future__ import annotations

import pytest

from backend.app.report.builder import NOT_VERIFIABLE, PENDING_VERIFICATION, build_report, render_markdown
from backend.app.report.service import ExperimentNotFound, ReportService

SPEC = {
    "experiment_id": "rep-1",
    "title": "Demo paper",
    "repository_url": "https://github.com/demo/project",
    "created_at": "2026-10-10T00:00:00+00:00",
    "dataset": "CIFAR-10",
    "optimizer": "Adam",
    "learning_rate": 0.001,
    "batch_size": 64,
    "epochs": 10,
    "seed": 42,
    "metrics": ["accuracy"],
    "architecture": "ResNet-18",
    "discrepancies": [
        {"field": "dataset", "status": "match", "paper_value": "CIFAR-10", "repository_value": "CIFAR-10"},
        {"field": "optimizer", "status": "conflict", "paper_value": "Adam", "repository_value": "SGD|momentum"},
    ],
    "validation": {"feasibility": "ready_with_limitations"},
    "repo": {"files": {"requirements.txt": "torch==2.1.0\n"}},
}


def _finding(rule_id: str, severity: str, status: str = "confirmed", evidence: bool = True, phase: str = "static") -> dict:
    return {
        "rule_id": rule_id,
        "phase": phase,
        "severity": severity,
        "status": status,
        "title": f"Title {rule_id}",
        "message": f"Message {rule_id}",
        "evidence": [{"source": "repository", "file_path": "train.py", "exact_text": "x"}] if evidence else [],
        "remediation": "Fix it.",
    }


def _audit(findings: list[dict], run: bool = False, llm: bool = False) -> dict:
    return {
        "experiment_id": "rep-1",
        "static": {"findings": findings},
        "llm": {"findings": []} if llm else None,
        "run": {"findings": []} if run else None,
        "findings": findings,
        "risk_score": {"score": 55, "bucket": "medium", "breakdown": []},
    }


def test_verdict_not_verifiable_without_runs() -> None:
    report = build_report(SPEC, _audit([]))
    assert report["verdict"]["status"] == NOT_VERIFIABLE
    assert any("No reproduction runs" in r for r in report["verdict"]["reasons"])


def test_verdict_lists_missing_critical_fields_even_with_runs() -> None:
    spec = {**SPEC, "dataset": None, "metrics": []}
    report = build_report(spec, _audit([], run=True))
    assert report["verdict"]["status"] == NOT_VERIFIABLE
    reasons = " ".join(report["verdict"]["reasons"])
    assert "dataset" in reasons and "evaluation metric" in reasons
    assert "No reproduction runs" not in reasons


def test_verdict_pending_when_runs_exist_and_fields_present() -> None:
    report = build_report(SPEC, _audit([], run=True))
    assert report["verdict"]["status"] == PENDING_VERIFICATION


def test_findings_sorted_by_severity_then_status() -> None:
    findings = [
        _finding("low_one", "low"),
        _finding("crit_possible", "critical", status="possible"),
        _finding("crit_confirmed", "critical"),
        _finding("med_one", "medium"),
    ]
    report = build_report(SPEC, _audit(findings))
    assert [f["rule_id"] for f in report["findings"]] == ["crit_confirmed", "crit_possible", "med_one", "low_one"]
    assert report["severity_counts"] == {"critical": 2, "high": 0, "medium": 1, "low": 1}


def test_findings_without_evidence_are_withheld_and_noted() -> None:
    findings = [_finding("with_ev", "high"), _finding("no_ev", "high", evidence=False)]
    report = build_report(SPEC, _audit(findings))
    assert [f["rule_id"] for f in report["findings"]] == ["with_ev"]
    assert any("1 finding(s) were withheld" in item for item in report["limitations"])


def test_only_non_matching_discrepancies_are_reported() -> None:
    report = build_report(SPEC, _audit([]))
    assert [d["field"] for d in report["discrepancies"]] == ["optimizer"]


def test_configuration_marks_missing_fields() -> None:
    report = build_report({**SPEC, "seed": None}, _audit([]))
    seed = next(row for row in report["configuration"] if row["field"] == "seed")
    assert seed["source"] == "missing"
    assert seed["critical"] is False


def test_limitations_for_no_repo_and_missing_phases() -> None:
    spec = {**SPEC, "repository_url": None, "repo": None}
    limitations = " ".join(build_report(spec, None)["limitations"])
    assert "No code repository" in limitations
    assert "LLM checks" in limitations
    assert "No run-phase audit" in limitations


def test_markdown_contains_sections_evidence_and_escapes_pipes() -> None:
    report = build_report(SPEC, _audit([_finding("missing_seed", "medium")]))
    markdown = render_markdown(report)
    for heading in ("## Verdict", "## Risk score", "## Experiment configuration", "## Paper vs code", "## Findings", "## Limitations of this report"):
        assert heading in markdown
    assert "55/100 (medium)" in markdown
    assert "(train.py)" in markdown
    assert "SGD\\|momentum" in markdown


def test_markdown_without_audit() -> None:
    markdown = render_markdown(build_report(SPEC, None))
    assert "No audit has been run." in markdown
    assert "No findings." in markdown


def _ingest(tmp_path) -> str:
    from backend.app.injestor.service import IngestionService

    spec = IngestionService(artifacts_dir=tmp_path).build(
        {"title": "Demo paper", "full_text": "We train a model.", "hash_sha256": "x", "evidence": []},
        None,
        repo_url=None,
    )
    return spec["experiment_id"]


def test_service_runs_static_audit_when_missing_and_persists(tmp_path, monkeypatch) -> None:
    from backend.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "")
    experiment_id = _ingest(tmp_path)
    service = ReportService(artifacts_dir=tmp_path)

    report = service.generate(experiment_id)
    assert report["risk_score"] is not None
    assert any(f["rule_id"] == "no_code_available" for f in report["findings"])
    assert any("LLM checks" in item for item in report["limitations"])
    assert service.get(experiment_id)["experiment_id"] == experiment_id
    assert service.get_markdown(experiment_id).startswith("# Reproducibility report: Demo paper")


def test_service_runs_llm_check_when_missing(tmp_path, monkeypatch) -> None:
    from backend.app.audit import service as audit_service_module
    from backend.config import settings

    monkeypatch.setattr(settings, "groq_api_key", "test-key")
    monkeypatch.setattr(audit_service_module, "check_ambiguous_claims", lambda context: [])
    experiment_id = _ingest(tmp_path)

    report = ReportService(artifacts_dir=tmp_path).generate(experiment_id)
    assert not any("LLM checks" in item for item in report["limitations"])


def test_service_raises_for_unknown_experiment(tmp_path) -> None:
    with pytest.raises(ExperimentNotFound):
        ReportService(artifacts_dir=tmp_path).generate("does-not-exist")


def test_report_routes_end_to_end(tmp_path, monkeypatch) -> None:
    from fastapi.testclient import TestClient

    from backend.app.main import app
    from backend.app.report import routes as report_routes

    monkeypatch.setattr(report_routes, "service", ReportService(artifacts_dir=tmp_path))
    experiment_id = _ingest(tmp_path)
    client = TestClient(app)

    assert client.get(f"/experiments/{experiment_id}/report").status_code == 404

    response = client.post(f"/experiments/{experiment_id}/report")
    assert response.status_code == 200
    assert response.json()["verdict"]["status"] == NOT_VERIFIABLE

    assert client.get(f"/experiments/{experiment_id}/report").status_code == 200

    response = client.get(f"/experiments/{experiment_id}/report.md")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "## Findings" in response.text

    assert client.post("/experiments/missing-id/report").status_code == 404


def _verified_audit(overall: str, verdict: str) -> dict:
    audit = _audit([], run=True)
    audit["run"]["claim_verification"] = {
        "overall": overall,
        "tolerance": 0.1,
        "reasons": [f"accuracy {verdict}"],
        "claims": [
            {"metric": "accuracy", "claimed_value": 91.2, "reproduced_mean": 90.1, "reproduced_std": 0.5,
             "seeds_run": 3, "gap": 0.012, "verdict": verdict},
        ],
    }
    return audit


def test_verdict_reproducible_when_claims_within_tolerance() -> None:
    from backend.app.report.builder import REPRODUCIBLE

    report = build_report(SPEC, _verified_audit("reproducible", "reproducible"))
    assert report["verdict"]["status"] == REPRODUCIBLE
    markdown = render_markdown(report)
    assert "## Claim verification" in markdown
    assert "within 10%" in markdown


def test_verdict_not_reproducible_when_claim_outside_tolerance() -> None:
    from backend.app.report.builder import NOT_REPRODUCIBLE

    report = build_report(SPEC, _verified_audit("not_reproducible", "not_reproducible"))
    assert report["verdict"]["status"] == NOT_REPRODUCIBLE


def test_missing_critical_fields_keep_not_verifiable_even_with_claim_verification() -> None:
    spec = {**SPEC, "dataset": None}
    report = build_report(spec, _verified_audit("reproducible", "reproducible"))
    assert report["verdict"]["status"] == NOT_VERIFIABLE
    assert "accuracy reproducible" in report["verdict"]["reasons"]
