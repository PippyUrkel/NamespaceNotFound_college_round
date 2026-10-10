from __future__ import annotations

from typing import Any

from .models import AuditContext, Evidence, RunSummary, SpecField

SPEC_FIELDS = [
    "dataset",
    "optimizer",
    "learning_rate",
    "batch_size",
    "epochs",
    "seed",
    "metrics",
    "architecture",
]


def _evidence_for(spec: dict[str, Any], field: str, source: str) -> list[Evidence]:
    items = []
    for raw in spec.get("evidence", []) or []:
        if raw.get("source") == source:
            items.append(Evidence(**{k: v for k, v in raw.items() if k in Evidence.model_fields}))
    return items


def _field_source(spec: dict[str, Any], field: str, value: Any) -> str:
    if value in (None, "", []):
        return "missing"
    return "paper"


def build_context(
    spec: dict[str, Any],
    *,
    paper_text: str = "",
    run_summaries: list[RunSummary] | None = None,
) -> AuditContext:
    fields: dict[str, SpecField] = {}
    for name in SPEC_FIELDS:
        value = spec.get(name)
        fields[name] = SpecField(
            value=value,
            source=_field_source(spec, name, value),
            evidence=_evidence_for(spec, name, "paper"),
        )

    repo = spec.get("repo") or None
    has_repo = bool(repo) or bool(spec.get("repository_url"))
    repo_files = dict((repo or {}).get("files") or {})
    repo_dependencies = list((repo or {}).get("dependencies") or [])

    if not paper_text:
        paper_text = "\n".join(
            str(item.get("exact_text"))
            for item in (spec.get("evidence") or [])
            if item.get("source") == "paper" and item.get("exact_text")
        )

    return AuditContext(
        experiment_id=spec["experiment_id"],
        fields=fields,
        paper_text=paper_text,
        discrepancies=list(spec.get("discrepancies") or []),
        has_repo=has_repo,
        repo_files=repo_files,
        repo_dependencies=repo_dependencies,
        run_summaries=run_summaries or [],
    )


__all__ = ["build_context", "SPEC_FIELDS"]
