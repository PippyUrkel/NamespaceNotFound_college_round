from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Literal
from pydantic import BaseModel, Field


class CodeProvenance(BaseModel):
    source: Literal[
        "repository",
        "paper",
        "reconciled",
        "paper_llm_generated",
        "deterministic_synthesis",
        "tuned",
        "assumed",
    ] = "paper_llm_generated"
    file_path: str | None = None
    confidence: float = 0.90
    evidence: str | None = None


class DAGNode(BaseModel):
    id: str
    name: str
    type: str
    description: str
    code: str
    upstream: list[str] = Field(default_factory=list)
    downstream: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)
    provenance: CodeProvenance = Field(default_factory=CodeProvenance)
    config_hash: str = ""
    status: Literal["ready", "modified", "needs_review", "unverified"] = "ready"

    def compute_hash(self) -> str:
        payload = {
            "id": self.id,
            "type": self.type,
            "code": self.code.strip(),
            "parameters": self.parameters,
            "upstream": sorted(self.upstream),
        }
        serialized = json.dumps(payload, sort_keys=True)
        return hashlib.sha256(serialized.encode("utf-8")).hexdigest()[:16]


class DAGEdge(BaseModel):
    source: str
    target: str
    data_flow: str | None = None


class GraphVersion(BaseModel):
    version_id: str
    parent_version: str | None = None
    created_at: str = Field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    change_description: str = "Initial graph generation from paper and repository analysis"
    nodes: list[DAGNode] = Field(default_factory=list)
    edges: list[DAGEdge] = Field(default_factory=list)
    execution_order: list[str] = Field(default_factory=list)
    graph_hash: str = ""
    parameters_summary: dict[str, Any] = Field(default_factory=dict)
    condition_provenance: dict[str, Any] = Field(default_factory=dict)

    def compute_graph_hash(self) -> str:
        hashes = [node.config_hash or node.compute_hash() for node in self.nodes]
        edge_repr = [f"{e.source}->{e.target}" for e in sorted(self.edges, key=lambda x: (x.source, x.target))]
        combined = f"{'|'.join(hashes)}::{'|'.join(edge_repr)}"
        return hashlib.sha256(combined.encode("utf-8")).hexdigest()[:16]


class TuneParameterRequest(BaseModel):
    node_id: str | None = None
    parameters: dict[str, Any] = Field(default_factory=dict)
    code_updates: dict[str, str] = Field(default_factory=dict)
    change_description: str | None = None


class GraphDiff(BaseModel):
    from_version: str
    to_version: str
    parameter_changes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    code_changes: dict[str, dict[str, str]] = Field(default_factory=dict)
    modified_nodes: list[str] = Field(default_factory=list)


class ValidationIssue(BaseModel):
    node_id: str
    node_name: str
    severity: Literal["error", "warning", "info"] = "error"
    category: Literal[
        "undefined_symbol",
        "syntax_error",
        "missing_import",
        "dependency_order_violation",
        "scope_isolation_gap",
    ] = "undefined_symbol"
    symbol: str | None = None
    line_number: int | None = None
    message: str
    suggested_fix: str | None = None


class NodeScopeSummary(BaseModel):
    node_id: str
    defined_symbols: list[str] = Field(default_factory=list)
    referenced_symbols: list[str] = Field(default_factory=list)
    imported_modules: list[str] = Field(default_factory=list)
    missing_symbols: list[str] = Field(default_factory=list)


class GraphValidationReport(BaseModel):
    is_valid: bool
    can_auto_remediate: bool = True
    total_errors: int = 0
    total_warnings: int = 0
    issues: list[ValidationIssue] = Field(default_factory=list)
    node_scopes: dict[str, NodeScopeSummary] = Field(default_factory=dict)
    sequential_execution_valid: bool = True
    sequential_simulation_error: str | None = None
    remediated_code_by_node: dict[str, str] = Field(default_factory=dict)

