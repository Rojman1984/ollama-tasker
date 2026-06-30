"""
tasker.workers.registry
-----------------------
WorkerRegistry and WorkerSelector.
See SDD Sections 5.4 and 5.5.
"""
from __future__ import annotations

from pathlib import Path

import yaml

from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    RoutingPolicy,
    PrivacyTier,
    TaskerPolicyError,
    WorkerManifest,
)

_LATENCY_RANK: dict[LatencyClass, int] = {
    LatencyClass.FAST: 0,
    LatencyClass.MEDIUM: 1,
    LatencyClass.SLOW: 2,
}

_LOCATION_COST_RANK: dict[ComputeLocation, int] = {
    ComputeLocation.LOCAL_HARDWARE: 0,
    ComputeLocation.OLLAMA_CLOUD:   1,
    ComputeLocation.DIRECT_CLOUD:   2,
}


class WorkerRegistry:
    """Catalog of all registered workers. Thread-safety is the caller's concern."""

    def __init__(self) -> None:
        self._workers: dict[str, WorkerManifest] = {}

    def register(self, manifest: WorkerManifest) -> None:
        self._workers[manifest.id] = manifest

    def deregister(self, worker_id: str) -> None:
        self._workers.pop(worker_id, None)

    def filter(self, capabilities: set[Capability]) -> list[WorkerManifest]:
        """Return all workers whose capability set is a superset of *capabilities*."""
        return [
            w for w in self._workers.values()
            if capabilities.issubset(w.capabilities)
        ]

    def health_check(self, worker_id: str) -> bool:
        """Return the stored `available` flag for the given worker."""
        worker = self._workers.get(worker_id)
        return worker.available if worker is not None else False

    def list_all(self) -> list[WorkerManifest]:
        return list(self._workers.values())

    def get(self, worker_id: str) -> WorkerManifest | None:
        return self._workers.get(worker_id)

    @classmethod
    def load_from_yaml(cls, path: Path) -> WorkerRegistry:
        """Load a WorkerRegistry from config/workers/worker_registry.yaml."""
        registry = cls()
        with path.open(encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
        for entry in data.get("workers", []):
            entry.setdefault("available", True)
            entry.setdefault("vram_mb", None)
            entry.setdefault("capability_scores", {})
            try:
                registry.register(WorkerManifest.from_dict(entry))
            except Exception:
                pass
        return registry


class WorkerSelector:
    """
    Stateless selector that applies the SDD 5.5 decision tree and returns the
    single best WorkerManifest from the supplied candidate pool.
    """

    @staticmethod
    def select(
        workers: list[WorkerManifest],
        required_capabilities: set[Capability],
        policy: RoutingPolicy,
        privacy_tier: PrivacyTier,
        slots_available: int,
        should_throttle: bool,
    ) -> WorkerManifest:
        """
        Apply the full selection pipeline and return the best worker.

        Raises TaskerPolicyError when no worker survives the pipeline.
        """
        candidates = [w for w in workers if w.available]

        # ------------------------------------------------------------------ #
        # 1. Privacy check
        # ------------------------------------------------------------------ #
        if privacy_tier == PrivacyTier.LOCAL_ONLY or policy == RoutingPolicy.PRIVATE:
            candidates = [
                w for w in candidates
                if w.compute_location == ComputeLocation.LOCAL_HARDWARE
            ]
            if not candidates:
                raise TaskerPolicyError(
                    "No LOCAL_HARDWARE workers available — privacy_tier=LOCAL_ONLY "
                    "or PRIVATE policy blocks all cloud compute"
                )
        elif privacy_tier == PrivacyTier.OLLAMA_CLOUD_OK:
            candidates = [
                w for w in candidates
                if w.compute_location != ComputeLocation.DIRECT_CLOUD
            ]

        # ------------------------------------------------------------------ #
        # 2. Concurrency check
        # ------------------------------------------------------------------ #
        if slots_available == 0:
            candidates = [
                w for w in candidates
                if w.compute_location != ComputeLocation.OLLAMA_CLOUD
            ]

        # ------------------------------------------------------------------ #
        # 3. Budget check — remove heavy Ollama Cloud workers when throttling,
        #    unless they are the only remaining option.
        # ------------------------------------------------------------------ #
        if should_throttle:
            preferred = [
                w for w in candidates
                if not (
                    w.compute_location == ComputeLocation.OLLAMA_CLOUD
                    and w.ollama_usage_level is not None
                    and w.ollama_usage_level >= 3
                )
            ]
            if preferred:
                candidates = preferred  # only heavy-cloud workers were penalized away

        # ------------------------------------------------------------------ #
        # 4. Capability filter
        # ------------------------------------------------------------------ #
        candidates = [
            w for w in candidates
            if required_capabilities.issubset(w.capabilities)
        ]

        if not candidates:
            raise TaskerPolicyError(
                f"No workers satisfy required_capabilities={required_capabilities!r}, "
                f"privacy_tier={privacy_tier.name}, policy={policy.name}"
            )

        # ------------------------------------------------------------------ #
        # 5. Policy rank
        # ------------------------------------------------------------------ #
        return WorkerSelector._rank(candidates, policy)

    @staticmethod
    def _rank(candidates: list[WorkerManifest], policy: RoutingPolicy) -> WorkerManifest:
        if policy == RoutingPolicy.COST_OPTIMIZED:
            return min(
                candidates,
                key=lambda w: (
                    _LOCATION_COST_RANK[w.compute_location],
                    w.ollama_usage_level if w.ollama_usage_level is not None else 0,
                    _LATENCY_RANK[w.latency_class],
                ),
            )

        if policy == RoutingPolicy.CAPABILITY_FIRST:
            return max(
                candidates,
                key=lambda w: sum(w.capability_scores.values()),
            )

        if policy == RoutingPolicy.SPEED_OPTIMIZED:
            return min(
                candidates,
                key=lambda w: (
                    _LATENCY_RANK[w.latency_class],
                    _LOCATION_COST_RANK[w.compute_location],
                ),
            )

        if policy in (RoutingPolicy.HYBRID, RoutingPolicy.PRIVATE):
            # Prefer local; within same location tier, prefer higher capability score.
            return min(
                candidates,
                key=lambda w: (
                    _LOCATION_COST_RANK[w.compute_location],
                    -sum(w.capability_scores.values()),
                ),
            )

        return candidates[0]
