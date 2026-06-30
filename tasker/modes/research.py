"""
tasker.modes.research
----------------------
RESEARCH mode -- deep research.
Parallel fetch + long-context synthesis. Citation tracking.
Workers: minimax-m3 (1M ctx) for synthesis, local for fetch steps.
See SDD Section 5.1.
"""
from __future__ import annotations

from tasker.modes.base import TaskerMode
from tasker.tools.bundles import RESEARCH_BUNDLE
from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    MemoryScope,
    PrivacyTier,
    RoutingPolicy,
)

RESEARCH_MODE = TaskerMode(
    name="research",
    orchestrator_tier_max=3,
    tool_bundle=RESEARCH_BUNDLE,
    routing_policy=RoutingPolicy.CAPABILITY_FIRST,
    interaction_pattern=InteractionPattern.ASYNC_STREAM,
    memory_scope=MemoryScope.RESEARCH_SESSION,
    worker_preference_order=[
        ComputeLocation.LOCAL_HARDWARE,
        ComputeLocation.OLLAMA_CLOUD,
        ComputeLocation.DIRECT_CLOUD,
    ],
    private_hard_block=False,
    privacy_tier=PrivacyTier.ANY_CLOUD,
)
