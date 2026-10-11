"""Seed coordinator — manages multi-seed independent execution.

Supports:
- Explicitly configured seeds (from paper/repo conditions)
- Default to at least 3 seeds when none specified
- Each seed is an independent run with its own status, metrics, logs
- Aggregation only from valid completed runs
- Incomplete statistics are clearly marked
"""
from __future__ import annotations

import math
from typing import Any

from .models import (
    AggregatedMetric,
    FailureReason,
    RunStatus,
    SeedRun,
    SeedRunMetrics,
)


class SeedCoordinator:
    """Coordinate multi-seed execution and aggregate results."""

    DEFAULT_SEEDS = [42, 123, 7]

    # ------------------------------------------------------------------
    # Seed resolution
    # ------------------------------------------------------------------
    @classmethod
    def resolve_seeds(
        cls,
        explicit_seeds: list[int] | None,
        condition_provenance: dict[str, Any] | None = None,
        min_seeds: int = 1,
        pad_explicit: bool = False,
    ) -> list[int]:
        """Determine which seeds to use.

        Priority:
        1. Explicitly requested seeds in the execution config (respected as-is unless pad_explicit=True)
        2. Seed picked up from the experiment condition provenance (single default seed)
        3. Default single seed [42]
        """
        if explicit_seeds:
            if not pad_explicit or len(explicit_seeds) >= min_seeds:
                return list(explicit_seeds)
            seeds = list(explicit_seeds)
        elif condition_provenance:
            seed_cond = condition_provenance.get("seed", {})
            provenance_seed = None
            if isinstance(seed_cond, dict) and seed_cond.get("value") is not None:
                try:
                    provenance_seed = int(seed_cond["value"])
                except (ValueError, TypeError):
                    pass
            seeds = [provenance_seed] if provenance_seed is not None else [cls.DEFAULT_SEEDS[0]]
        else:
            seeds = [cls.DEFAULT_SEEDS[0]] if min_seeds == 1 else list(cls.DEFAULT_SEEDS)

        # Pad to min_seeds if needed
        next_seed = 1000
        while len(seeds) < min_seeds:
            while next_seed in seeds:
                next_seed += 1
            seeds.append(next_seed)
            next_seed += 1

        return seeds

    # ------------------------------------------------------------------
    # Seed run initialization
    # ------------------------------------------------------------------
    @classmethod
    def create_seed_runs(cls, seeds: list[int]) -> list[SeedRun]:
        """Create SeedRun objects for each seed, all pending."""
        return [SeedRun(seed=seed) for seed in seeds]

    # ------------------------------------------------------------------
    # Aggregation — only from valid completed runs
    # ------------------------------------------------------------------
    @classmethod
    def aggregate_metrics(cls, seed_runs: list[SeedRun]) -> list[AggregatedMetric]:
        """Aggregate metrics across completed seed runs only.

        Failed, timed-out, or cancelled runs are excluded from aggregation.
        Results are clearly marked as complete or incomplete.
        Failed runs are NEVER treated as zero-valued measurements.
        """
        completed = [
            sr for sr in seed_runs
            if sr.status == RunStatus.completed
        ]
        total = len(seed_runs)

        if not completed:
            return []

        # Collect all metric names across completed runs
        all_metric_names: set[str] = set()
        for sr in completed:
            all_metric_names.update(sr.metrics.values.keys())

        aggregated: list[AggregatedMetric] = []
        for metric_name in sorted(all_metric_names):
            values: list[float] = []
            seeds: list[int] = []
            for sr in completed:
                if metric_name in sr.metrics.values:
                    values.append(sr.metrics.values[metric_name])
                    seeds.append(sr.seed)

            if not values:
                continue

            is_complete = len(values) == total
            mean_val = sum(values) / len(values)

            # Standard deviation
            if len(values) > 1:
                variance = sum((v - mean_val) ** 2 for v in values) / (len(values) - 1)
                std_val = math.sqrt(variance)
            else:
                std_val = None

            note = ""
            if not is_complete:
                failed_count = total - len(completed)
                note = (
                    f"Statistics computed from {len(values)}/{total} completed runs. "
                    f"{failed_count} run(s) excluded due to failure/timeout/cancellation. "
                    f"These incomplete statistics should be interpreted with caution."
                )

            aggregated.append(
                AggregatedMetric(
                    metric_name=metric_name,
                    values=values,
                    seeds=seeds,
                    mean=mean_val,
                    std=std_val,
                    min_val=min(values),
                    max_val=max(values),
                    num_completed=len(values),
                    num_total=total,
                    is_complete=is_complete,
                    note=note,
                )
            )

        return aggregated

    # ------------------------------------------------------------------
    # Status summary
    # ------------------------------------------------------------------
    @classmethod
    def summarize_runs(cls, seed_runs: list[SeedRun]) -> dict[str, Any]:
        """Produce a summary of seed run statuses."""
        status_counts: dict[str, int] = {}
        for sr in seed_runs:
            status_counts[sr.status.value] = status_counts.get(sr.status.value, 0) + 1

        failure_reasons: dict[str, int] = {}
        for sr in seed_runs:
            if sr.failure_reason != FailureReason.none:
                failure_reasons[sr.failure_reason.value] = (
                    failure_reasons.get(sr.failure_reason.value, 0) + 1
                )

        return {
            "total_seeds": len(seed_runs),
            "status_counts": status_counts,
            "failure_reasons": failure_reasons,
            "all_completed": all(sr.status == RunStatus.completed for sr in seed_runs),
            "any_completed": any(sr.status == RunStatus.completed for sr in seed_runs),
        }
