from __future__ import annotations

from typing import Any

from . import rules  # noqa: F401
from .models import AuditContext, Finding, Phase
from .rules import REGISTRY


def run_audit(context: AuditContext, phase: Phase, *, rule_kwargs: dict[str, dict[str, Any]] | None = None) -> list[Finding]:
    rule_kwargs = rule_kwargs or {}
    findings: list[Finding] = []
    for spec in REGISTRY:
        if spec.phase != phase:
            continue
        kwargs = rule_kwargs.get(spec.rule_id, {})
        for finding in spec.func(context, **kwargs):
            findings.append(finding.model_copy(update={"phase": phase}))
    return findings


__all__ = ["run_audit"]
