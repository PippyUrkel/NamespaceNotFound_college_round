from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

Severity = Literal["low", "medium", "high", "critical"]
Status = Literal["confirmed", "possible"]
Phase = Literal["static", "run"]
FieldSource = Literal["paper", "repository", "assumed", "missing"]


class Evidence(BaseModel):
    source: Literal["paper", "repository", "run", "assumed"] = "paper"
    section: str | None = None
    file_path: str | None = None
    page_number: int | None = None
    exact_text: str | None = None
    url: str | None = None


class Finding(BaseModel):
    rule_id: str
    phase: Phase
    severity: Severity
    status: Status
    title: str
    message: str
    evidence: list[Evidence] = Field(default_factory=list)
    remediation: str | None = None


class SpecField(BaseModel):
    value: Any = None
    source: FieldSource = "missing"
    evidence: list[Evidence] = Field(default_factory=list)

    @property
    def is_missing(self) -> bool:
        return self.source == "missing" or self.value in (None, "", [])

    @property
    def is_assumed(self) -> bool:
        return self.source == "assumed"


class RunSummary(BaseModel):
    metric: str
    claimed_value: float | None = None
    claimed_improvement: float | None = None
    reproduced_mean: float | None = None
    reproduced_std: float | None = None
    seeds_run: int = 0
    used_assumed_values: bool = False


class AuditContext(BaseModel):
    experiment_id: str
    fields: dict[str, SpecField] = Field(default_factory=dict)
    paper_text: str = ""
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)
    has_repo: bool = False
    repo_files: dict[str, str] = Field(default_factory=dict)
    repo_dependencies: list[str] = Field(default_factory=list)
    run_summaries: list[RunSummary] = Field(default_factory=list)

    def field(self, name: str) -> SpecField:
        return self.fields.get(name, SpecField())

    model_config = {"frozen": True}


class RiskScore(BaseModel):
    score: int
    bucket: Literal["low", "medium", "high"]
    breakdown: list[dict[str, Any]] = Field(default_factory=list)


__all__ = [
    "Severity",
    "Status",
    "Phase",
    "FieldSource",
    "Evidence",
    "Finding",
    "SpecField",
    "RunSummary",
    "AuditContext",
    "RiskScore",
]
