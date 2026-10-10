from __future__ import annotations

from .models import Finding, RiskScore

SEVERITY_WEIGHTS = {"critical": 40, "high": 25, "medium": 15, "low": 5}
STATUS_MULTIPLIER = {"confirmed": 1.0, "possible": 0.5}

LOW_MAX = 33
MEDIUM_MAX = 66


def score(findings: list[Finding]) -> RiskScore:
    breakdown = []
    total = 0.0
    for finding in findings:
        weight = SEVERITY_WEIGHTS[finding.severity] * STATUS_MULTIPLIER[finding.status]
        total += weight
        breakdown.append(
            {
                "rule_id": finding.rule_id,
                "severity": finding.severity,
                "status": finding.status,
                "weight": weight,
            }
        )

    capped = min(int(round(total)), 100)
    if capped <= LOW_MAX:
        bucket = "low"
    elif capped <= MEDIUM_MAX:
        bucket = "medium"
    else:
        bucket = "high"

    return RiskScore(score=capped, bucket=bucket, breakdown=breakdown)


__all__ = ["score", "SEVERITY_WEIGHTS", "STATUS_MULTIPLIER"]
