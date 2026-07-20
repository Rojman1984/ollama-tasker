"""
tasker.workers.registry
-----------------------
WorkerRegistry and WorkerSelector.
See SDD Sections 5.4 and 5.5.
"""
from __future__ import annotations

import logging
from pathlib import Path

import yaml

from tasker.config.gpu_backends import GPUInfo
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    RoutingPolicy,
    PrivacyTier,
    TaskerPolicyError,
    WorkerManifest,
)

logger = logging.getLogger(__name__)

# Phase 7.5.6 (SDD_ADDENDUM_7.5.md A.3.4): AMD APU / unified-memory reserve.
# gpu.memory_mb for a unified-memory GPU is TOTAL SYSTEM RAM (see GPUInfo
# docstring in tasker.config.gpu_backends) -- the full pool is never actually
# available to one process, so subtract a reserve before comparing against a
# worker's declared vram_mb. 6GB sits in A.3.4's recommended 4-8GB range.
_UNIFIED_MEMORY_RESERVE_MB = 6_144

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

    def apply_gpu_availability(
        self, gpu: GPUInfo | None, *, reserve_mb: int = _UNIFIED_MEMORY_RESERVE_MB,
    ) -> None:
        """
        Cross-check every requires_gpu=True worker against the resolved
        GPUInfo's usable memory (SDD_ADDENDUM_7.5.md A.3.4). A worker that
        doesn't fit is marked available=False with a logged reason -- never
        silently dropped, still visible via list_all()/`tasker workers`.

          - gpu is None (no GPU detected): every requires_gpu=True worker is
            marked unavailable.
          - NVIDIA (discrete, is_unified_memory=False): checked directly
            against gpu.memory_mb -- true dedicated VRAM.
          - AMD APU (unified memory, is_unified_memory=True): gpu.memory_mb
            is TOTAL SYSTEM RAM, not a dedicated pool -- reserve_mb is
            subtracted before comparing against the worker's declared
            vram_mb, since the full pool is never actually available to one
            process.

        Workers with requires_gpu=False are never touched by this method.
        """
        for worker in self._workers.values():
            if not worker.requires_gpu:
                continue

            if gpu is None:
                worker.available = False
                logger.warning(
                    "Worker '%s' marked unavailable -- requires_gpu=True "
                    "but no GPU was detected on this machine.", worker.id,
                )
                continue

            usable_mb = gpu.memory_mb or 0
            if gpu.is_unified_memory:
                usable_mb = max(0, usable_mb - reserve_mb)

            required_mb = worker.vram_mb or 0
            if required_mb > usable_mb:
                worker.available = False
                logger.warning(
                    "Worker '%s' marked unavailable -- requires %d MB VRAM, "
                    "only %d MB usable on this %s GPU%s.",
                    worker.id, required_mb, usable_mb, gpu.vendor,
                    " (unified memory, reserve applied)" if gpu.is_unified_memory else "",
                )

    def apply_provider_availability(self, provider_map: dict) -> None:
        """
        Cross-check every worker's declared provider against the wired
        provider_map (e.g. {ProviderType.OLLAMA: OllamaProvider(...)}) for
        the current entry point. A worker whose provider has no wired
        implementation is marked available=False with a logged reason --
        never silently dropped, same pattern as apply_gpu_availability --
        so WorkerSelector excludes it up front instead of being selected
        and then failing mid-dispatch with "No provider for X" after a
        step has already been planned around it.
        """
        for worker in self._workers.values():
            if worker.provider not in provider_map:
                worker.available = False
                logger.warning(
                    "Worker '%s' marked unavailable -- no wired provider for "
                    "'%s' in the active provider_map.",
                    worker.id, worker.provider.value,
                )

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
