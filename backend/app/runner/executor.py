"""Graph executor — topological execution of DAG nodes with caching.

Walks the experiment graph in dependency order. For each seed:
1. Checks cache for each node
2. If cache miss, delegates to DockerWorker
3. Stores result in cache
4. Propagates upstream outputs to downstream nodes
5. On upstream failure, marks downstream as failed (dependency_failure)

Never silently modifies scientific parameters. If a node fails, it's
recorded honestly with the actual failure reason.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from .cache import ExecutionCache
from .docker_worker import DockerWorker
from .models import (
    ExecutionConfig,
    ExecutionStatus,
    FailureReason,
    NodeExecutionConfig,
    NodeRunResult,
    ProgressEvent,
    RunStatus,
    SeedRun,
    SeedRunMetrics,
)

try:
    from backend.app.graph.models import DAGEdge, DAGNode, GraphVersion
except ModuleNotFoundError:  # pragma: no cover
    from app.graph.models import DAGEdge, DAGNode, GraphVersion


class GraphExecutor:
    """Execute a validated, immutable experiment graph."""

    def __init__(
        self,
        work_dir: Path,
        cache: ExecutionCache | None = None,
        docker_worker: DockerWorker | None = None,
        config: ExecutionConfig | None = None,
        on_progress: Callable[[ProgressEvent], None] | None = None,
    ) -> None:
        self._work_dir = work_dir
        self._work_dir.mkdir(parents=True, exist_ok=True)
        self._config = config or ExecutionConfig()
        self._cache = cache
        self._docker_worker = docker_worker or DockerWorker(
            work_dir=work_dir / "docker_runs",
            docker_image=self._config.docker_image,
        )
        self._on_progress = on_progress
        self._cancelled = False

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def execute_seed(
        self,
        graph: GraphVersion,
        seed: int,
    ) -> SeedRun:
        """Execute the entire graph once with a given seed.

        Returns a SeedRun with per-node results, metrics, and status.
        """
        seed_run = SeedRun(
            seed=seed,
            status=RunStatus.running,
            started_at=datetime.now(timezone.utc).isoformat(),
        )

        self._emit(ProgressEvent(
            event_type="seed_start",
            seed=seed,
            message=f"Starting execution with seed {seed}",
        ))

        node_map = {n.id: n for n in graph.nodes}
        adjacency = self._build_adjacency(graph)
        execution_order = graph.execution_order or self._topological_sort(graph)

        # Track which nodes have failed — downstream of failures skip
        failed_nodes: set[str] = set()
        node_results: dict[str, NodeRunResult] = {}
        all_metrics: dict[str, float] = {}

        for node_id in execution_order:
            if self._cancelled:
                seed_run.status = RunStatus.cancelled
                break

            node = node_map.get(node_id)
            if node is None:
                continue

            # Check if any upstream has failed
            upstream_failed = any(u in failed_nodes for u in node.upstream)
            if upstream_failed:
                result = NodeRunResult(
                    node_id=node_id,
                    status=RunStatus.failed,
                    failure_reason=FailureReason.upstream_failure,
                    failure_detail=f"Upstream node(s) failed: {[u for u in node.upstream if u in failed_nodes]}",
                    started_at=datetime.now(timezone.utc).isoformat(),
                    completed_at=datetime.now(timezone.utc).isoformat(),
                    runtime_seconds=0.0,
                    exit_code=-1,
                )
                failed_nodes.add(node_id)
                node_results[node_id] = result
                self._emit(ProgressEvent(
                    event_type="node_skipped",
                    seed=seed,
                    node_id=node_id,
                    message=f"Skipped: upstream failure",
                ))
                continue

            # Check cache
            node_config_hash = node.config_hash or node.compute_hash()
            upstream_hashes = [
                (node_map[u].config_hash or node_map[u].compute_hash())
                for u in node.upstream
                if u in node_map
            ]

            if self._cache and self._config.enable_cache:
                cached_result = self._cache.lookup(
                    node_id=node_id,
                    seed=seed,
                    node_config_hash=node_config_hash,
                    upstream_hashes=upstream_hashes,
                )
                if cached_result is not None:
                    cached_result.cache_hit = True
                    node_results[node_id] = cached_result
                    all_metrics.update(cached_result.metrics)
                    self._emit(ProgressEvent(
                        event_type="node_cache_hit",
                        seed=seed,
                        node_id=node_id,
                        message=f"Cache hit for {node.name}",
                    ))
                    continue

            # Execute the node
            self._emit(ProgressEvent(
                event_type="node_start",
                seed=seed,
                node_id=node_id,
                message=f"Executing {node.name}",
            ))

            # Resolve per-node config
            node_exec_config = self._config.node_configs.get(
                node_id,
                NodeExecutionConfig(
                    node_id=node_id,
                    timeout_seconds=self._config.default_timeout_seconds,
                    memory_limit_mb=self._config.default_memory_limit_mb,
                    cpu_limit=self._config.default_cpu_limit,
                    max_retries=self._config.max_retries,
                ),
            )

            # Inject seed into environment
            node_exec_config.environment["CRISISGRID_SEED"] = str(seed)
            node_exec_config.environment["PYTHONHASHSEED"] = str(seed)

            # Upstream outputs directory
            upstream_dir = self._work_dir / f"seed_{seed}" / "outputs"
            upstream_dir.mkdir(parents=True, exist_ok=True)

            # Assemble upstream prerequisite code in topological order for chained execution
            ancestors = self._get_ancestors(node_id, graph)
            upstream_code_parts = [
                f"# --- Upstream dependency: {anc_id} ---\n{node_map[anc_id].code}"
                for anc_id in execution_order
                if anc_id in ancestors and anc_id in node_map
            ]
            upstream_code = "\n\n".join(upstream_code_parts) if upstream_code_parts else None

            # Execute with retries
            result = self._execute_with_retries(
                node=node,
                seed=seed,
                config=node_exec_config,
                upstream_dir=upstream_dir,
                max_retries=node_exec_config.max_retries,
                upstream_code=upstream_code,
            )

            node_results[node_id] = result

            if result.status == RunStatus.completed:
                all_metrics.update(result.metrics)
                # Store in cache
                if self._cache and self._config.enable_cache:
                    self._cache.store(
                        node_id=node_id,
                        seed=seed,
                        graph_hash=graph.graph_hash,
                        node_config_hash=node_config_hash,
                        upstream_hashes=upstream_hashes,
                        result=result,
                    )
                self._emit(ProgressEvent(
                    event_type="node_complete",
                    seed=seed,
                    node_id=node_id,
                    message=f"Completed {node.name}",
                    data={"metrics": result.metrics},
                ))
            else:
                failed_nodes.add(node_id)
                self._emit(ProgressEvent(
                    event_type="node_failed",
                    seed=seed,
                    node_id=node_id,
                    message=f"Failed: {result.failure_reason.value} — {result.failure_detail}",
                ))

        # Finalize seed run
        completed_at = datetime.now(timezone.utc).isoformat()
        seed_run.completed_at = completed_at
        seed_run.node_results = node_results
        seed_run.metrics = SeedRunMetrics(values=all_metrics)
        seed_run.runtime_seconds = self._calc_runtime(seed_run.started_at or "", completed_at)

        if self._cancelled:
            seed_run.status = RunStatus.cancelled
        elif not failed_nodes:
            seed_run.status = RunStatus.completed
        else:
            # Determine the most specific failure reason
            failure_reasons = [
                node_results[nid].failure_reason
                for nid in failed_nodes
                if nid in node_results and node_results[nid].failure_reason != FailureReason.upstream_failure
            ]
            if any(r == FailureReason.timeout for r in failure_reasons):
                seed_run.status = RunStatus.timed_out
                seed_run.failure_reason = FailureReason.timeout
            elif any(r == FailureReason.oom for r in failure_reasons):
                seed_run.status = RunStatus.resource_exhausted
                seed_run.failure_reason = FailureReason.oom
            else:
                seed_run.status = RunStatus.failed
                seed_run.failure_reason = (
                    failure_reasons[0] if failure_reasons else FailureReason.unknown
                )
            seed_run.failure_detail = f"Failed nodes: {list(failed_nodes)}"

        self._emit(ProgressEvent(
            event_type="seed_complete",
            seed=seed,
            message=f"Seed {seed} finished: {seed_run.status.value}",
            data={"metrics": all_metrics},
        ))

        return seed_run

    def cancel(self) -> None:
        """Cancel the current execution."""
        self._cancelled = True

    # ------------------------------------------------------------------
    # Retry logic
    # ------------------------------------------------------------------
    def _execute_with_retries(
        self,
        node: DAGNode,
        seed: int,
        config: NodeExecutionConfig,
        upstream_dir: Path,
        max_retries: int = 1,
        upstream_code: str | None = None,
    ) -> NodeRunResult:
        """Execute a node with bounded retries for transient failures."""
        last_result: NodeRunResult | None = None

        for attempt in range(max_retries + 1):
            result = self._docker_worker.execute_node(
                node_id=node.id,
                code=node.code,
                seed=seed,
                parameters=node.parameters,
                config=config,
                upstream_outputs_dir=upstream_dir,
                pip_packages=self._config.pip_packages,
                upstream_code=upstream_code,
            )

            if result.status == RunStatus.completed:
                return result

            last_result = result

            # Don't retry on non-transient failures
            if result.failure_reason in (
                FailureReason.invalid_configuration,
                FailureReason.dataset_unavailable,
            ):
                break

            if attempt < max_retries:
                self._emit(ProgressEvent(
                    event_type="node_retry",
                    seed=seed,
                    node_id=node.id,
                    message=f"Retrying {node.name} (attempt {attempt + 2}/{max_retries + 1})",
                ))

        return last_result or NodeRunResult(
            node_id=node.id,
            status=RunStatus.failed,
            failure_reason=FailureReason.unknown,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _get_ancestors(self, node_id: str, graph: GraphVersion) -> set[str]:
        """Collect all transitive upstream ancestors for a given node."""
        node_map = {n.id: n for n in graph.nodes}
        ancestors: set[str] = set()
        to_visit = list(node_map[node_id].upstream) if node_id in node_map else []
        while to_visit:
            curr = to_visit.pop()
            if curr not in ancestors:
                ancestors.add(curr)
                if curr in node_map:
                    to_visit.extend(node_map[curr].upstream)
        return ancestors
    def _build_adjacency(self, graph: GraphVersion) -> dict[str, list[str]]:
        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
            adj.setdefault(edge.source, []).append(edge.target)
        return adj

    def _topological_sort(self, graph: GraphVersion) -> list[str]:
        in_degree = {n.id: 0 for n in graph.nodes}
        adj: dict[str, list[str]] = {n.id: [] for n in graph.nodes}
        for edge in graph.edges:
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
        for n in graph.nodes:
            if n.id not in order:
                order.append(n.id)
        return order

    def _emit(self, event: ProgressEvent) -> None:
        if self._on_progress:
            self._on_progress(event)

    @staticmethod
    def _calc_runtime(started: str, completed: str) -> float:
        try:
            t1 = datetime.fromisoformat(started)
            t2 = datetime.fromisoformat(completed)
            return (t2 - t1).total_seconds()
        except Exception:
            return 0.0
