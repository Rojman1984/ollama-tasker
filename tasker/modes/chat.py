"""
tasker.modes.chat
------------------
CHAT mode -- lightweight conversational.
Orchestrator: Tier 0-1, single worker, no planning loop.
Routing: COST_OPTIMIZED. Interaction: sync stream.
See SDD Section 5.1.
"""
from __future__ import annotations

from tasker.modes.base import TaskerMode
from tasker.tools.bundles import CHAT_BUNDLE
from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    MemoryScope,
    PrivacyTier,
    RoutingPolicy,
)

CHAT_MODE = TaskerMode(
    name="chat",
    orchestrator_tier_max=1,
    tool_bundle=CHAT_BUNDLE,
    routing_policy=RoutingPolicy.COST_OPTIMIZED,
    interaction_pattern=InteractionPattern.SYNC_STREAM,
    memory_scope=MemoryScope.SESSION,
    worker_preference_order=[
        ComputeLocation.LOCAL_HARDWARE,
        ComputeLocation.OLLAMA_CLOUD,
        ComputeLocation.DIRECT_CLOUD,
    ],
    private_hard_block=False,
    privacy_tier=PrivacyTier.ANY_CLOUD,
)
