from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

try:
    from backend.app.audit.context import SPEC_FIELDS
    from backend.app.audit.rules import CRITICAL_FIELDS
except ModuleNotFoundError:  # pragma: no cover
    from app.audit.context import SPEC_FIELDS
    from app.audit.rules import CRITICAL_FIELDS

SEVERITY_ORDER = {"critical": 0, "high": 1, "medium": 2, "low": 3}
STATUS_ORDER = {"confirmed": 0, "possible": 1}

NOT_VERIFIABLE = "Not verifiable"
PENDING_VERIFICATION = "Pending verification"
REPRODUCIBLE = "Reproducible"
NOT_REPRODUCIBLE = "Not reproducible"

_CLAIM_VERDICTS = {
    "reproducible": REPRODUCIBLE,
    "not_reproducible": NOT_REPRODUCIBLE,
    "not_verifiable": NOT_VERIFIABLE,
}


def _is_missing(value: Any) -> bool:
    return value in (None, "", [])


def _configuration(spec: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "field": name,
            "value": spec.get(name),
            "source": "missing" if _is_missing(spec.get(name)) else "paper",
            "critical": name in CRITICAL_FIELDS,
        }
        for name in SPEC_FIELDS
    ]


def _verdict(spec: dict[str, Any], audit: dict[str, Any] | None) -> dict[str, Any]:
    reasons = [
        f"Critical field not stated: {label}."
        for name, label in CRITICAL_FIELDS.items()
        if _is_missing(spec.get(name))
    ]
    has_runs = bool(audit and audit.get("run"))
    if not has_runs:
        reasons.append("No reproduction runs have been performed.")
    verification = _claim_verification(audit)
    if reasons:
        # Missing critical fields mean the run used assumed values, so its outcome cannot settle the claim.
        return {"status": NOT_VERIFIABLE, "reasons": reasons + (verification or {}).get("reasons", [])}
    if verification:
        return {
            "status": _CLAIM_VERDICTS.get(verification.get("overall"), NOT_VERIFIABLE),
            "reasons": list(verification.get("reasons") or []),
        }
    return {
        "status": PENDING_VERIFICATION,
        "reasons": ["Reproduction runs exist, but no verification verdict has been computed yet."],
    }


def _claim_verification(audit: dict[str, Any] | None) -> dict[str, Any] | None:
    return ((audit or {}).get("run") or {}).get("claim_verification")


def _sorted_findings(findings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return sorted(
        findings,
        key=lambda f: (SEVERITY_ORDER.get(f.get("severity"), 9), STATUS_ORDER.get(f.get("status"), 9), f.get("rule_id", "")),
    )


def _limitations(spec: dict[str, Any], audit: dict[str, Any] | None, withheld: int) -> list[str]:
    items = []
    repo = spec.get("repo") or {}
    if not spec.get("repository_url") and not repo:
        items.append("No code repository was available, so repository checks were skipped.")
    elif not repo.get("files"):
        items.append("A repository URL was given but no repository files were inspected, so repository checks are unreliable.")
    if not spec.get("full_text") and not (spec.get("paper") or {}).get("full_text"):
        items.append("The full paper text is not stored; text-based checks ran on evidence excerpts only and may miss issues.")
    items.append("Field sources are inferred: the ingested spec does not record per-field provenance yet.")
    if not audit or not audit.get("llm"):
        items.append("LLM checks (ambiguous metrics, missing baselines, leakage hints) were not run.")
    if not audit or not audit.get("run"):
        items.append("No run-phase audit: reproduced results have not been compared with the paper's claims.")
    elif not spec.get("claimed_results"):
        items.append("No numeric results were extracted from the paper, so reproduced metrics could not be compared with claims.")
    for limitation in ((audit or {}).get("run") or {}).get("execution_limitations") or []:
        if limitation.get("detail"):
            items.append(f"Execution: {limitation['detail']}")
    if withheld:
        items.append(f"{withheld} finding(s) were withheld because they had no evidence.")
    return items


def build_report(spec: dict[str, Any], audit: dict[str, Any] | None) -> dict[str, Any]:
    raw_findings = list((audit or {}).get("findings") or [])
    findings = _sorted_findings([f for f in raw_findings if f.get("evidence")])
    withheld = len(raw_findings) - len(findings)

    severity_counts = {level: 0 for level in SEVERITY_ORDER}
    for finding in findings:
        severity_counts[finding["severity"]] = severity_counts.get(finding["severity"], 0) + 1

    return {
        "experiment_id": spec["experiment_id"],
        "title": spec.get("title") or "Untitled paper",
        "repository_url": spec.get("repository_url"),
        "ingested_at": spec.get("created_at"),
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verdict": _verdict(spec, audit),
        "claim_verification": _claim_verification(audit),
        "configuration": _configuration(spec),
        "feasibility": spec.get("validation") or {},
        "discrepancies": [d for d in spec.get("discrepancies") or [] if d.get("status") != "match"],
        "risk_score": (audit or {}).get("risk_score"),
        "severity_counts": severity_counts,
        "findings": findings,
        "limitations": _limitations(spec, audit, withheld),
    }


def _cell(value: Any, limit: int = 120) -> str:
    if _is_missing(value):
        return "—"
    text = ", ".join(map(str, value)) if isinstance(value, list) else str(value)
    text = " ".join(text.split()).replace("|", "\\|")
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _evidence_line(item: dict[str, Any]) -> str:
    location = [
        part
        for part in (
            item.get("section"),
            item.get("file_path"),
            f"page {item['page_number']}" if item.get("page_number") else None,
            item.get("url"),
        )
        if part
    ]
    line = f"- *{item.get('source', 'unknown')}*"
    if location:
        line += f" ({', '.join(location)})"
    if item.get("exact_text"):
        line += f": \"{_cell(item['exact_text'], 200)}\""
    return line


def render_markdown(report: dict[str, Any]) -> str:
    lines = [f"# Reproducibility report: {report['title']}", ""]
    lines.append(f"- Experiment: `{report['experiment_id']}`")
    lines.append(f"- Repository: {report['repository_url'] or 'none'}")
    lines.append(f"- Generated: {report['generated_at']}")
    lines.append("")

    verdict = report["verdict"]
    lines += ["## Verdict", "", f"**{verdict['status']}**", ""]
    lines += [f"- {reason}" for reason in verdict["reasons"]]
    lines.append("")

    risk = report.get("risk_score")
    lines += ["## Risk score", ""]
    if risk:
        counts = ", ".join(f"{n} {level}" for level, n in report["severity_counts"].items() if n)
        lines.append(f"**{risk['score']}/100 ({risk['bucket']})**" + (f" from {counts} finding(s)." if counts else "."))
    else:
        lines.append("No audit has been run.")
    lines.append("")

    verification = report.get("claim_verification")
    if verification and verification.get("claims"):
        lines += [
            "## Claim verification",
            "",
            f"A claim counts as reproduced when the reproduced mean is within {verification['tolerance']:.0%} of the paper's value.",
            "",
            "| Metric | Claimed | Reproduced (mean ± std) | Gap | Verdict |",
            "|---|---|---|---|---|",
        ]
        for claim in verification["claims"]:
            reproduced = "—"
            if claim.get("reproduced_mean") is not None:
                reproduced = f"{claim['reproduced_mean']:.4g}"
                if claim.get("reproduced_std") is not None:
                    reproduced += f" ± {claim['reproduced_std']:.2g}"
                reproduced += f" ({claim.get('seeds_run', 0)} seed(s))"
            gap = f"{claim['gap']:.1%}" if claim.get("gap") is not None else "—"
            verdict = _CLAIM_VERDICTS.get(claim.get("verdict"), NOT_VERIFIABLE)
            lines.append(f"| {_cell(claim.get('metric'))} | {claim.get('claimed_value'):g} | {reproduced} | {gap} | {verdict} |")
        lines.append("")

    lines += ["## Experiment configuration", "", "| Field | Value | Source |", "|---|---|---|"]
    for row in report["configuration"]:
        name = row["field"] + (" *" if row["critical"] else "")
        lines.append(f"| {name} | {_cell(row['value'])} | {row['source']} |")
    lines += ["", "\\* critical for reproduction", ""]

    if report["discrepancies"]:
        lines += ["## Paper vs code", "", "| Field | Status | Paper | Repository |", "|---|---|---|---|"]
        for item in report["discrepancies"]:
            lines.append(
                f"| {item.get('field')} | {item.get('status')} | {_cell(item.get('paper_value'))} | {_cell(item.get('repository_value'))} |"
            )
        lines.append("")

    lines += ["## Findings", ""]
    if not report["findings"]:
        lines += ["No findings.", ""]
    for finding in report["findings"]:
        lines.append(f"### [{finding['severity'].upper()} · {finding['status']}] {finding['title']}")
        lines += ["", finding["message"], "", "Evidence:"]
        lines += [_evidence_line(item) for item in finding["evidence"]]
        if finding.get("remediation"):
            lines += ["", f"Remediation: {finding['remediation']}"]
        lines += ["", f"<sub>rule `{finding['rule_id']}` · {finding['phase']} phase</sub>", ""]

    lines += ["## Limitations of this report", ""]
    lines += [f"- {item}" for item in report["limitations"]]
    lines.append("")
    return "\n".join(lines)


__all__ = [
    "build_report",
    "render_markdown",
    "NOT_VERIFIABLE",
    "PENDING_VERIFICATION",
    "REPRODUCIBLE",
    "NOT_REPRODUCIBLE",
]
