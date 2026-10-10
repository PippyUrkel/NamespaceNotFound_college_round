"""Hash-based execution cache with downstream invalidation.

Caches node execution results keyed by (node_id, seed, config_hash,
upstream_hashes).  When an upstream node's configuration changes, all
downstream cache entries are automatically invalidated.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import CacheEntry, NodeRunResult


class ExecutionCache:
    """File-backed execution cache stored under the experiment directory."""

    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)
        self._index_file = self._cache_dir / "cache_index.json"
        self._index: dict[str, dict[str, Any]] = self._load_index()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def lookup(
        self,
        node_id: str,
        seed: int,
        node_config_hash: str,
        upstream_hashes: list[str],
    ) -> NodeRunResult | None:
        """Return cached result or None."""
        key = CacheEntry.compute_cache_key(node_id, seed, node_config_hash, upstream_hashes)
        if key not in self._index:
            return None
        entry_path = self._cache_dir / f"{key}.json"
        if not entry_path.exists():
            # Stale index entry
            del self._index[key]
            self._save_index()
            return None
        try:
            raw = json.loads(entry_path.read_text(encoding="utf-8"))
            entry = CacheEntry.model_validate(raw)
            return entry.result
        except Exception:
            return None

    def store(
        self,
        node_id: str,
        seed: int,
        graph_hash: str,
        node_config_hash: str,
        upstream_hashes: list[str],
        result: NodeRunResult,
    ) -> str:
        """Store a result and return its cache key."""
        key = CacheEntry.compute_cache_key(node_id, seed, node_config_hash, upstream_hashes)
        entry = CacheEntry(
            cache_key=key,
            node_id=node_id,
            seed=seed,
            graph_hash=graph_hash,
            node_config_hash=node_config_hash,
            upstream_hashes=upstream_hashes,
            result=result,
        )
        entry_path = self._cache_dir / f"{key}.json"
        entry_path.write_text(
            json.dumps(entry.model_dump(), indent=2),
            encoding="utf-8",
        )
        self._index[key] = {
            "node_id": node_id,
            "seed": seed,
            "node_config_hash": node_config_hash,
        }
        self._save_index()
        return key

    def invalidate_node(self, node_id: str) -> list[str]:
        """Invalidate all cache entries for a node (any seed). Returns removed keys."""
        removed: list[str] = []
        keys_to_remove = [
            k for k, v in self._index.items() if v.get("node_id") == node_id
        ]
        for key in keys_to_remove:
            entry_path = self._cache_dir / f"{key}.json"
            if entry_path.exists():
                entry_path.unlink()
            removed.append(key)
            del self._index[key]
        if removed:
            self._save_index()
        return removed

    def invalidate_downstream(
        self,
        changed_node_id: str,
        adjacency: dict[str, list[str]],
    ) -> list[str]:
        """Invalidate cache for a node and all its downstream dependents."""
        # BFS from changed_node_id through the adjacency graph
        visited: set[str] = set()
        queue = [changed_node_id]
        all_removed: list[str] = []

        while queue:
            nid = queue.pop(0)
            if nid in visited:
                continue
            visited.add(nid)
            all_removed.extend(self.invalidate_node(nid))
            for downstream in adjacency.get(nid, []):
                if downstream not in visited:
                    queue.append(downstream)

        return all_removed

    def clear(self) -> int:
        """Clear entire cache. Returns count of removed entries."""
        count = len(self._index)
        for key in list(self._index.keys()):
            entry_path = self._cache_dir / f"{key}.json"
            if entry_path.exists():
                entry_path.unlink()
        self._index.clear()
        self._save_index()
        return count

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------
    def _load_index(self) -> dict[str, dict[str, Any]]:
        if self._index_file.exists():
            try:
                return json.loads(self._index_file.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_index(self) -> None:
        self._index_file.write_text(
            json.dumps(self._index, indent=2),
            encoding="utf-8",
        )
