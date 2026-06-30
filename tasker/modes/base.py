"""
tasker.modes.base
------------------
TaskerMode dataclass and ModeConfigurator.

ModeConfigurator: HardwareProfile x TaskerMode -> ExecutionConfig.
Applies plan-level mode_constraints from the hardware profile YAML
(e.g. Free plan forces COWORK into sequential_only on TASKER-P1).
See SDD Sections 5.1, 8.1, and 8.4.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import yaml

from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    MemoryScope,
    OllamaPlan,
    PrivacyTier,
    RoutingPolicy,
    TaskerConfigError,
    ToolID,
)


# --------------------------------------------------------------------------- #
# String → enum maps (used by from_dict loaders)
# --------------------------------------------------------------------------- #

_POLICY_MAP: dict[str, RoutingPolicy] = {
    "cost_optimized":   RoutingPolicy.COST_OPTIMIZED,
    "capability_first": RoutingPolicy.CAPABILITY_FIRST,
    "speed_optimized":  RoutingPolicy.SPEED_OPTIMIZED,
    "hybrid":           RoutingPolicy.HYBRID,
    "private":          RoutingPolicy.PRIVATE,
}

_INTERACTION_MAP: dict[str, InteractionPattern] = {
    "sync_stream":      InteractionPattern.SYNC_STREAM,
    "cli_repl":         InteractionPattern.CLI_REPL,
    "async_checkpoint": InteractionPattern.ASYNC_CHECKPOINT,
    "async_stream":     InteractionPattern.ASYNC_STREAM,
}

_MEMORY_MAP: dict[str, MemoryScope] = {
    "session":            MemoryScope.SESSION,
    "project_aware":      MemoryScope.PROJECT_AWARE,
    "project_episodic":   MemoryScope.PROJECT_EPISODIC,
    "research_session":   MemoryScope.RESEARCH_SESSION,
    "local_filesystem":   MemoryScope.LOCAL_FILESYSTEM,
}

_PRIVACY_MAP: dict[str, PrivacyTier] = {
    "local_only":      PrivacyTier.LOCAL_ONLY,
    "ollama_cloud_ok": PrivacyTier.OLLAMA_CLOUD_OK,
    "any_cloud":       PrivacyTier.ANY_CLOUD,
}

_PLAN_MAP: dict[str, OllamaPlan] = {
    "free": OllamaPlan.FREE,
    "pro":  OllamaPlan.PRO,
    "max":  OllamaPlan.MAX,
}


# --------------------------------------------------------------------------- #
# TaskerMode  (SDD 6.7)
# --------------------------------------------------------------------------- #

@dataclass
class TaskerMode:
    """
    Declarative mode configuration.
    Combine with a HardwareProfile via ModeConfigurator to get ExecutionConfig.
    """
    name: str
    orchestrator_tier_max: int
    tool_bundle: frozenset[ToolID]
    routing_policy: RoutingPolicy
    interaction_pattern: InteractionPattern
    memory_scope: MemoryScope
    worker_preference_order: list[ComputeLocation]
    private_hard_block: bool
    privacy_tier: PrivacyTier

    @classmethod
    def from_dict(cls, data: dict) -> TaskerMode:
        """Construct from a loaded mode YAML dict."""
        def _require(key: str, mapping: dict, label: str) -> object:
            val = data.get(key)
            result = mapping.get(str(val).lower() if val else "")
            if result is None:
                raise TaskerConfigError(f"Unknown {label}: {val!r}")
            return result

        policy      = _require("routing_policy",    _POLICY_MAP,      "routing_policy")
        interaction = _require("interaction_pattern", _INTERACTION_MAP, "interaction_pattern")
        memory      = _require("memory_scope",       _MEMORY_MAP,      "memory_scope")
        privacy     = _require("privacy_tier",       _PRIVACY_MAP,     "privacy_tier")

        raw_bundle = data.get("tool_bundle") or []
        try:
            bundle = frozenset(ToolID(t) for t in raw_bundle)
        except ValueError as exc:
            raise TaskerConfigError(f"Unknown tool in bundle: {exc}") from exc

        # Default worker preference order derived from privacy tier
        if privacy == PrivacyTier.LOCAL_ONLY:
            pref: list[ComputeLocation] = [ComputeLocation.LOCAL_HARDWARE]
        elif privacy == PrivacyTier.OLLAMA_CLOUD_OK:
            pref = [ComputeLocation.LOCAL_HARDWARE, ComputeLocation.OLLAMA_CLOUD]
        else:
            pref = [
                ComputeLocation.LOCAL_HARDWARE,
                ComputeLocation.OLLAMA_CLOUD,
                ComputeLocation.DIRECT_CLOUD,
            ]

        return cls(
            name=data["name"],
            orchestrator_tier_max=int(data.get("orchestrator_tier_max", 1)),
            tool_bundle=bundle,
            routing_policy=policy,              # type: ignore[arg-type]
            interaction_pattern=interaction,    # type: ignore[arg-type]
            memory_scope=memory,                # type: ignore[arg-type]
            worker_preference_order=pref,
            private_hard_block=bool(data.get("private_hard_block", False)),
            privacy_tier=privacy,               # type: ignore[arg-type]
        )


# --------------------------------------------------------------------------- #
# HardwareProfile  (SDD 8.2)
# --------------------------------------------------------------------------- #

@dataclass
class HardwareProfile:
    """Loaded from config/profiles/<name>.yaml."""
    name: str
    description: str
    orchestrator_tier_max: int
    orchestrator_model: str
    ollama_plan: OllamaPlan
    max_concurrent_local: int
    max_concurrent_ollama_cloud: int
    unload_between_tasks: bool
    ollama_base_url: str
    session_throttle_at: float
    weekly_throttle_at: float
    mode_constraints: dict[str, dict]   # mode_name -> {"behavior": str, ...}

    @classmethod
    def from_dict(cls, data: dict) -> HardwareProfile:
        orch   = data.get("orchestrator", {})
        pool   = data.get("worker_pool", {})
        ollama = data.get("ollama", {})
        plan   = _PLAN_MAP.get(str(ollama.get("plan", "free")).lower(), OllamaPlan.FREE)
        return cls(
            name=data.get("hardware_profile", "unknown"),
            description=data.get("description", ""),
            orchestrator_tier_max=int(orch.get("tier_max", 0)),
            orchestrator_model=str(orch.get("model", "qwen3:1.7b")),
            ollama_plan=plan,
            max_concurrent_local=int(pool.get("max_concurrent_local", 1)),
            max_concurrent_ollama_cloud=int(pool.get("max_concurrent_ollama_cloud", 0)),
            unload_between_tasks=bool(pool.get("unload_between_tasks", True)),
            ollama_base_url=str(ollama.get("base_url", "http://localhost:11434")),
            session_throttle_at=float(ollama.get("session_throttle_at", 0.90)),
            weekly_throttle_at=float(ollama.get("weekly_throttle_at", 0.85)),
            mode_constraints=data.get("mode_constraints") or {},
        )


# --------------------------------------------------------------------------- #
# ExecutionConfig  (resolved output)
# --------------------------------------------------------------------------- #

@dataclass
class ExecutionConfig:
    """
    Resolved configuration for a single run.
    ModeConfigurator merges a HardwareProfile and TaskerMode into this.
    """
    mode: TaskerMode
    profile: HardwareProfile
    effective_tier_max: int          # min(mode.tier_max, profile.tier_max)
    cowork_behavior: str             # "sequential_only" | "limited_parallel" | "full_parallel"
    research_behavior: str           # "single_worker" | "parallel_fetch"


# --------------------------------------------------------------------------- #
# ModeConfigurator  (SDD 8.1)
# --------------------------------------------------------------------------- #

_REPO_ROOT = Path(__file__).parent.parent.parent


class ModeConfigurator:
    """
    Combines a HardwareProfile and a TaskerMode into a resolved ExecutionConfig.

    Hardware profile's orchestrator.tier_max caps the mode's orchestrator_tier_max —
    the harness never tries to spin up a tier the hardware cannot support.
    mode_constraints from the profile override default concurrency behavior.
    """

    def __init__(
        self,
        profiles_dir: Path | None = None,
        modes_dir: Path | None = None,
    ) -> None:
        self._profiles_dir = profiles_dir or (_REPO_ROOT / "config" / "profiles")
        self._modes_dir    = modes_dir    or (_REPO_ROOT / "config" / "modes")

    def load_profile(self, profile_name: str) -> HardwareProfile:
        path = self._profiles_dir / f"{profile_name}.yaml"
        if not path.exists():
            raise TaskerConfigError(f"Hardware profile not found: {path}")
        with path.open(encoding="utf-8") as fh:
            return HardwareProfile.from_dict(yaml.safe_load(fh))

    def resolve_hardware_profile(self, explicit_profile: str | None = None) -> HardwareProfile:
        """
        Three-source resolution order (SDD_ADDENDUM_7.5.md A.3.1):
          1. explicit_profile arg or TASKER_PROFILE env var -> load_profile(name)
          2. machine-local cache (.tasker/hardware_profile.json), only if its
             recorded hostname matches this machine
          3. live detection (slower; prints a suggestion to cache it)
        All three paths return the same HardwareProfile type -- downstream
        consumers don't need to know which source was used. Local import to
        avoid a module-load-time cycle (tasker.config.detect imports
        HardwareProfile from this module).
        """
        import os

        from tasker.config.detect import detect_hardware_profile, load_cached_detection

        name = explicit_profile or os.environ.get("TASKER_PROFILE") or None
        if name:
            return self.load_profile(name)

        cached = load_cached_detection()
        if cached is not None:
            return cached

        print(
            "No cached hardware detection found (or hostname mismatch) -- "
            "running live detection. Run `tasker-hardware detect` once to "
            "cache this for faster startup."
        )
        return detect_hardware_profile()

    def load_mode(self, mode_name: str) -> TaskerMode:
        path = self._modes_dir / f"{mode_name}.yaml"
        if not path.exists():
            raise TaskerConfigError(f"Mode config not found: {path}")
        with path.open(encoding="utf-8") as fh:
            return TaskerMode.from_dict(yaml.safe_load(fh))

    def resolve(self, profile: HardwareProfile, mode: TaskerMode) -> ExecutionConfig:
        """
        Merge profile hardware constraints into mode, return ExecutionConfig.
        Hardware tier_max is a hard ceiling — modes cannot exceed what hardware supports.
        """
        effective_tier = min(mode.orchestrator_tier_max, profile.orchestrator_tier_max)
        constraints    = profile.mode_constraints

        cowork_behavior   = constraints.get("cowork",   {}).get("behavior", "full_parallel")
        research_behavior = constraints.get("research", {}).get("behavior", "parallel_fetch")

        return ExecutionConfig(
            mode=mode,
            profile=profile,
            effective_tier_max=effective_tier,
            cowork_behavior=cowork_behavior,
            research_behavior=research_behavior,
        )

    def build(self, profile_name: str, mode_name: str) -> ExecutionConfig:
        """Load both from YAML and return a resolved ExecutionConfig."""
        return self.resolve(self.load_profile(profile_name), self.load_mode(mode_name))
