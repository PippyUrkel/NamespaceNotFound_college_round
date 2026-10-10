from __future__ import annotations

import re
from typing import Any

from .models import RunSummary

# A reproduced result within 10% (relative) of the paper's claimed value counts as reproduced.
REPRODUCIBILITY_TOLERANCE = 0.10

_EPSILON = 1e-9

_METRIC_ALIASES = {
    "acc": "accuracy",
    "top1": "accuracy",
    "top1accuracy": "accuracy",
    "testaccuracy": "accuracy",
    "f1score": "f1",
    "macrof1": "f1",
    "meanaverageprecision": "map",
    "rocauc": "auc",
    "aucroc": "auc",
}

# Metrics that papers report either as a fraction (0.92) or a percentage (92.0).
_PERCENT_METRICS = {"accuracy", "top5accuracy", "f1", "precision", "recall", "auc", "map"}


def canonical_metric(name: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", (name or "").lower())
    return _METRIC_ALIASES.get(key, key)


def relative_gap(claimed: float, reproduced: float) -> float:
    denom = abs(claimed) if claimed else _EPSILON
    return abs(reproduced - claimed) / denom


def within_tolerance(gap: float, tolerance: float = REPRODUCIBILITY_TOLERANCE) -> bool:
    return gap <= tolerance + _EPSILON


def _align_scale(metric: str, claimed: float, reproduced: float | None, std: float | None) -> tuple[float | None, float | None]:
    """Put the reproduced value on the paper's scale (fraction vs percentage) for percent-style metrics."""
    if reproduced is None or canonical_metric(metric) not in _PERCENT_METRICS:
        return reproduced, std
    if claimed > 1 and reproduced <= 1:
        return reproduced * 100, (std * 100 if std is not None else None)
    if claimed <= 1 and reproduced > 1:
        return reproduced / 100, (std / 100 if std is not None else None)
    return reproduced, std


def run_summaries_from_execution(
    claimed_results: list[dict[str, Any]],
    aggregated_metrics: list[dict[str, Any]],
    *,
    execution_id: str | None = None,
    used_assumed_values: bool = False,
) -> list[RunSummary]:
    """Pair each claimed paper result with the runner's aggregated metric of the same name."""
    reproduced_by_metric = {canonical_metric(m.get("metric_name", "")): m for m in aggregated_metrics}
    summaries: list[RunSummary] = []
    seen: set[str] = set()
    for claim in claimed_results:
        key = canonical_metric(str(claim.get("metric", "")))
        if not key or key in seen or claim.get("value") is None:
            continue
        seen.add(key)
        claimed_value = float(claim["value"])
        aggregated = reproduced_by_metric.get(key) or {}
        mean, std = _align_scale(key, claimed_value, aggregated.get("mean"), aggregated.get("std"))
        summaries.append(
            RunSummary(
                metric=str(claim.get("metric")),
                claimed_value=claimed_value,
                reproduced_mean=mean,
                reproduced_std=std,
                seeds_run=int(aggregated.get("num_completed") or 0),
                used_assumed_values=used_assumed_values,
                claim_quote=claim.get("exact_text"),
                execution_id=execution_id,
            )
        )
    return summaries


def verify_claims(run_summaries: list[RunSummary], tolerance: float = REPRODUCIBILITY_TOLERANCE) -> dict[str, Any]:
    """Per-claim and overall verdict: reproducible if the reproduced mean is within `tolerance` of the claim."""
    claims = []
    for run in run_summaries:
        if run.claimed_value is None:
            continue
        entry: dict[str, Any] = {
            "metric": run.metric,
            "claimed_value": run.claimed_value,
            "reproduced_mean": run.reproduced_mean,
            "reproduced_std": run.reproduced_std,
            "seeds_run": run.seeds_run,
            "used_assumed_values": run.used_assumed_values,
            "claim_quote": run.claim_quote,
            "execution_id": run.execution_id,
            "gap": None,
            "tolerance": tolerance,
        }
        if run.reproduced_mean is None or run.seeds_run == 0:
            entry["verdict"] = "not_verifiable"
            entry["reason"] = f"No completed run reported {run.metric}, so the claim could not be checked."
        else:
            gap = relative_gap(run.claimed_value, run.reproduced_mean)
            entry["gap"] = gap
            if within_tolerance(gap, tolerance):
                entry["verdict"] = "reproducible"
                entry["reason"] = (
                    f"Reproduced {run.metric} {run.reproduced_mean:.4g} is within {gap:.1%} of the claimed "
                    f"{run.claimed_value:g} (tolerance {tolerance:.0%})."
                )
            else:
                entry["verdict"] = "not_reproducible"
                entry["reason"] = (
                    f"Reproduced {run.metric} {run.reproduced_mean:.4g} differs from the claimed "
                    f"{run.claimed_value:g} by {gap:.1%}, beyond the {tolerance:.0%} tolerance."
                )
        claims.append(entry)

    verdicts = {c["verdict"] for c in claims}
    if "not_reproducible" in verdicts:
        overall = "not_reproducible"
    elif verdicts == {"reproducible"}:
        overall = "reproducible"
    else:
        overall = "not_verifiable"

    reasons = [c["reason"] for c in claims]
    if not claims:
        reasons = ["No numeric result claimed by the paper could be paired with a reproduction run."]
    return {"overall": overall, "tolerance": tolerance, "claims": claims, "reasons": reasons}


__all__ = [
    "REPRODUCIBILITY_TOLERANCE",
    "canonical_metric",
    "relative_gap",
    "within_tolerance",
    "run_summaries_from_execution",
    "verify_claims",
]
