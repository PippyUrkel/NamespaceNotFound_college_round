from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class EvidenceReference(BaseModel):
    source: Literal["paper", "repository", "assumed", "missing"] = "paper"
    section: str | None = None
    file_path: str | None = None
    page_number: int | None = None
    exact_text: str | None = None
    url: str | None = None


class FieldValue(BaseModel):
    value: Any = None
    source: Literal["paper", "repository", "assumed", "missing"] = "missing"
    evidence: list[EvidenceReference] = Field(default_factory=list)
    confidence: float | None = None
    conflicts: list[Any] = Field(default_factory=list)


class ExperimentResult(BaseModel):
    experiment_id: str
    title: str | None = None
    repository_url: str | None = None
    pdf_sha256: str | None = None
    status: str = "created"
    dataset: str | None = None
    optimizer: str | None = None
    learning_rate: float | None = None
    batch_size: int | None = None
    epochs: int | None = None
    seed: int | None = None
    metrics: list[str] = Field(default_factory=list)
    architecture: str | None = None
    evidence: list[EvidenceReference] = Field(default_factory=list)
    discrepancies: list[dict[str, Any]] = Field(default_factory=list)
    artifact_path: str | None = None
    created_at: str | None = None
    validation: dict[str, Any] = Field(default_factory=dict)
