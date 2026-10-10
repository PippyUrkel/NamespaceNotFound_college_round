from __future__ import annotations

import difflib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    from backend.config import settings
except ModuleNotFoundError:  # pragma: no cover
    from config import settings

from .generator import GraphCodeGenerator
from .models import DAGEdge, DAGNode, GraphDiff, GraphVersion, TuneParameterRequest


class GraphService:
    def __init__(self, artifacts_dir: str | Path | None = None) -> None:
        self._custom_artifacts_dir = Path(artifacts_dir) if artifacts_dir else None

    @property
    def artifacts_dir(self) -> Path:
        if self._custom_artifacts_dir:
            return self._custom_artifacts_dir
        return Path(settings.artifacts_dir)

    def _get_experiment_dir(self, experiment_id: str) -> Path:
        return self.artifacts_dir / "experiments" / experiment_id

    def _get_versions_file(self, experiment_id: str) -> Path:
        return self._get_experiment_dir(experiment_id) / "graph_versions.json"

    def _load_spec(self, experiment_id: str) -> dict[str, Any] | None:
        spec_file = self._get_experiment_dir(experiment_id) / "experiment_spec.json"
        if not spec_file.exists():
            return None
        return json.loads(spec_file.read_text(encoding="utf-8"))

    def get_or_create_graph(self, experiment_id: str) -> GraphVersion | None:
        versions_file = self._get_versions_file(experiment_id)
        if versions_file.exists():
            try:
                data = json.loads(versions_file.read_text(encoding="utf-8"))
                if data and isinstance(data, list):
                    latest_raw = data[-1]
                    return GraphVersion.model_validate(latest_raw)
            except Exception as exc:
                print(f"[GraphService] Error loading graph versions: {exc}", flush=True)

        # Generate initial v1 graph
        return self.generate_graph(experiment_id)

    def generate_graph(self, experiment_id: str, force: bool = False) -> GraphVersion | None:
        spec = self._load_spec(experiment_id)
        if spec is None:
            return None

        exp_dir = self._get_experiment_dir(experiment_id)
        exp_dir.mkdir(parents=True, exist_ok=True)
        versions_file = self._get_versions_file(experiment_id)

        if not force and versions_file.exists():
            try:
                data = json.loads(versions_file.read_text(encoding="utf-8"))
                if data:
                    return GraphVersion.model_validate(data[-1])
            except Exception:
                pass

        repo_analysis = spec.get("repo")
        paper_analysis = spec.get("paper")
        from .parameters import ExperimentConditionResolver

        conditions = ExperimentConditionResolver.resolve_conditions(spec, paper_analysis, repo_analysis)
        nodes, edges = GraphCodeGenerator.generate_dag(
            spec, repo_analysis, paper_analysis=paper_analysis, conditions=conditions
        )
        execution_order = self._topological_sort(nodes, edges)

        param_summary: dict[str, Any] = {}
        for n in nodes:
            param_summary.update(n.parameters)

        v1 = GraphVersion(
            version_id="v1",
            parent_version=None,
            created_at=datetime.now(timezone.utc).isoformat(),
            change_description="Initial DAG code block synthesis from paper & repository context",
            nodes=nodes,
            edges=edges,
            execution_order=execution_order,
            parameters_summary=param_summary,
            condition_provenance=conditions.model_dump(),
        )
        v1.graph_hash = v1.compute_graph_hash()

        # Save to graph_versions.json
        versions = [v1.model_dump()]
        versions_file.write_text(json.dumps(versions, indent=2), encoding="utf-8")

        # Save active graph file
        active_graph_file = exp_dir / "experiment_graph.json"
        active_graph_file.write_text(json.dumps(v1.model_dump(), indent=2), encoding="utf-8")

        # Also update spec.json dag block for backward compatibility
        try:
            spec_file = exp_dir / "experiment_spec.json"
            spec["dag"] = {
                "nodes": [n.model_dump() for n in nodes],
                "edges": [e.model_dump() for e in edges],
                "execution_order": execution_order,
                "version_id": "v1",
                "graph_hash": v1.graph_hash,
            }
            spec_file.write_text(json.dumps(spec, indent=2), encoding="utf-8")
        except Exception:
            pass

        return v1

    def tune_graph(self, experiment_id: str, request: TuneParameterRequest) -> GraphVersion:
        current = self.get_or_create_graph(experiment_id)
        if current is None:
            raise ValueError(f"Experiment {experiment_id} not found.")

        # Determine next version id
        versions = self.get_all_versions(experiment_id)
        next_ver_num = len(versions) + 1
        new_version_id = f"v{next_ver_num}"

        # Deep copy nodes
        new_nodes: list[DAGNode] = [DAGNode.model_validate(n.model_dump()) for n in current.nodes]
        param_changes_desc: list[str] = []

        # 1. Update parameters across nodes
        for param_key, param_value in request.parameters.items():
            param_changes_desc.append(f"{param_key}={param_value}")
            for node in new_nodes:
                # If target node matches or parameter belongs to node
                if request.node_id is None or node.id == request.node_id:
                    if param_key in node.parameters or request.node_id == node.id:
                        node.parameters[param_key] = param_value
                        node.code = self._update_code_parameter(node.code, param_key, param_value)
                        node.provenance.source = "tuned"
                        node.status = "modified"

        # 2. Update custom code if specified
        for node_id, custom_code in request.code_updates.items():
            for node in new_nodes:
                if node.id == node_id:
                    node.code = custom_code
                    node.provenance.source = "tuned"
                    node.status = "modified"
                    param_changes_desc.append(f"custom code for {node_id}")

        # Recompute node hashes
        for node in new_nodes:
            node.config_hash = node.compute_hash()

        # Update summary
        new_params_summary = dict(current.parameters_summary)
        new_params_summary.update(request.parameters)

        # Update condition provenance for tuned parameters
        new_condition_provenance = dict(current.condition_provenance) if current.condition_provenance else {}
        for param_key, param_value in request.parameters.items():
            if param_key in new_condition_provenance and isinstance(new_condition_provenance[param_key], dict):
                cond_dict = dict(new_condition_provenance[param_key])
                cond_dict["value"] = param_value
                cond_dict["source"] = "tuned"
                cond_dict["is_assumed"] = False
                cond_dict["evidence"] = f"Fine-tuned by user to {param_value}"
                new_condition_provenance[param_key] = cond_dict

        desc = request.change_description or (
            f"Tuned: {', '.join(param_changes_desc)}" if param_changes_desc else "Manual parameters fine-tuning"
        )

        new_version = GraphVersion(
            version_id=new_version_id,
            parent_version=current.version_id,
            created_at=datetime.now(timezone.utc).isoformat(),
            change_description=desc,
            nodes=new_nodes,
            edges=current.edges,
            execution_order=current.execution_order,
            parameters_summary=new_params_summary,
            condition_provenance=new_condition_provenance,
        )
        new_version.graph_hash = new_version.compute_graph_hash()

        # Save immutably
        versions_file = self._get_versions_file(experiment_id)
        raw_versions = [v.model_dump() for v in versions]
        raw_versions.append(new_version.model_dump())
        versions_file.write_text(json.dumps(raw_versions, indent=2), encoding="utf-8")

        # Save active graph
        exp_dir = self._get_experiment_dir(experiment_id)
        active_graph_file = exp_dir / "experiment_graph.json"
        active_graph_file.write_text(json.dumps(new_version.model_dump(), indent=2), encoding="utf-8")

        return new_version

    def get_all_versions(self, experiment_id: str) -> list[GraphVersion]:
        versions_file = self._get_versions_file(experiment_id)
        if not versions_file.exists():
            initial = self.get_or_create_graph(experiment_id)
            return [initial] if initial else []
        try:
            data = json.loads(versions_file.read_text(encoding="utf-8"))
            return [GraphVersion.model_validate(v) for v in data]
        except Exception:
            return []

    def get_version(self, experiment_id: str, version_id: str) -> GraphVersion | None:
        versions = self.get_all_versions(experiment_id)
        for v in versions:
            if v.version_id == version_id:
                return v
        return None

    def diff_versions(
        self,
        experiment_id: str,
        from_version_id: str | None = None,
        to_version_id: str | None = None,
    ) -> GraphDiff:
        versions = self.get_all_versions(experiment_id)
        if not versions:
            raise ValueError(f"No graph versions found for experiment {experiment_id}")

        v_map = {v.version_id: v for v in versions}
        to_v = v_map.get(to_version_id) if to_version_id else versions[-1]
        if to_v is None:
            raise ValueError(f"Version {to_version_id} not found")

        from_v = v_map.get(from_version_id) if from_version_id else None
        if from_v is None:
            if to_v.parent_version and to_v.parent_version in v_map:
                from_v = v_map[to_v.parent_version]
            else:
                from_v = versions[0]

        # Parameter diffs
        param_diffs: dict[str, dict[str, Any]] = {}
        all_keys = set(from_v.parameters_summary.keys()) | set(to_v.parameters_summary.keys())
        for k in all_keys:
            old_val = from_v.parameters_summary.get(k)
            new_val = to_v.parameters_summary.get(k)
            if old_val != new_val:
                param_diffs[k] = {"old": old_val, "new": new_val}

        # Code diffs & modified nodes
        code_diffs: dict[str, dict[str, str]] = {}
        modified_nodes: list[str] = []
        old_nodes_map = {n.id: n for n in from_v.nodes}
        new_nodes_map = {n.id: n for n in to_v.nodes}

        for nid, new_node in new_nodes_map.items():
            old_node = old_nodes_map.get(nid)
            if old_node is None or old_node.config_hash != new_node.config_hash:
                modified_nodes.append(nid)
                old_code = old_node.code if old_node else ""
                diff = difflib.unified_diff(
                    old_code.splitlines(),
                    new_node.code.splitlines(),
                    fromfile=f"{from_v.version_id}/{nid}",
                    tofile=f"{to_v.version_id}/{nid}",
                    lineterm="",
                )
                code_diffs[nid] = {
                    "unified_diff": "\n".join(diff),
                    "old_hash": old_node.config_hash if old_node else "",
                    "new_hash": new_node.config_hash,
                }

        return GraphDiff(
            from_version=from_v.version_id,
            to_version=to_v.version_id,
            parameter_changes=param_diffs,
            code_changes=code_diffs,
            modified_nodes=modified_nodes,
        )

    @staticmethod
    def _update_code_parameter(code: str, key: str, value: Any) -> str:
        val_repr = repr(value) if isinstance(value, str) else str(value)
        # 1. Variable assignment: key = ...
        p1 = rf"^(\s*{re.escape(key)}\s*=\s*)(.+)$"
        updated, c1 = re.subn(p1, rf"\g<1>{val_repr}", code, flags=re.MULTILINE)
        if c1 > 0:
            return updated
        # 2. Function default argument or definition: key: int = ... or key=...
        p2 = rf"(\b{re.escape(key)}\s*(?::\s*[^=]+)?=\s*)([^,\)\n]+)"
        updated, c2 = re.subn(p2, rf"\g<1>{val_repr}", code)
        if c2 > 0:
            return updated
        # 3. Dict entry: 'key': ...
        p3 = rf"([\"']{re.escape(key)}[\"']\s*:\s*)([^,\n}}]+)"
        updated, c3 = re.subn(p3, rf"\g<1>{val_repr}", code)
        if c3 > 0:
            return updated
        # Fallback header assignment
        return f"# Parameter update: {key} = {val_repr}\n{key} = {val_repr}\n{code}"

    @staticmethod
    def _topological_sort(nodes: list[DAGNode], edges: list[DAGEdge]) -> list[str]:
        node_map = {n.id: n for n in nodes}
        in_degree = {n.id: 0 for n in nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in nodes}

        for edge in edges:
            adj[edge.source].append(edge.target)
            in_degree[edge.target] = in_degree.get(edge.target, 0) + 1

        queue = [nid for nid, deg in in_degree.items() if deg == 0]
        order: list[str] = []

        while queue:
            curr = queue.pop(0)
            order.append(curr)
            for neighbor in adj.get(curr, []):
                in_degree[neighbor] -= 1
                if in_degree[neighbor] == 0:
                    queue.append(neighbor)

        # Append any remaining disconnected nodes
        for n in nodes:
            if n.id not in order:
                order.append(n.id)
        return order
