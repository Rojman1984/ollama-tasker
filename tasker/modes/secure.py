"""
tasker.modes.secure
--------------------
SECURE mode -- LOCAL_ONLY hard block.
ANY cloud call raises TaskerPolicyError immediately.
No silent fallback. Banner shown on every response.
See SDD Sections 5.1 and 11.
"""
from __future__ import annotations

from tasker.modes.base import TaskerMode
from tasker.tools.bundles import SECURE_BUNDLE
from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    MemoryScope,
    PrivacyTier,
    RoutingPolicy,
)

# SECURE mode passes PrivacyTier.LOCAL_ONLY to WorkerSelector, which already
# enforces the hard block -- no reimplementation needed here.
SECURE_MODE = TaskerMode(
    name="secure",
    orchestrator_tier_max=1,
    tool_bundle=SECURE_BUNDLE,
    routing_policy=RoutingPolicy.PRIVATE,
    interaction_pattern=InteractionPattern.SYNC_STREAM,
    memory_scope=MemoryScope.LOCAL_FILESYSTEM,
    worker_preference_order=[ComputeLocation.LOCAL_HARDWARE],
    private_hard_block=True,
    privacy_tier=PrivacyTier.LOCAL_ONLY,
)
