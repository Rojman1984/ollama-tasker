"""
tasker.workers.registry
-----------------------
WorkerRegistry and WorkerSelector.
See SDD Sections 5.4 and 5.5.
"""
from __future__ import annotations

# TODO Phase 1
#
# WorkerRegistry:
#   register(manifest) -- validates, stores
#   deregister(worker_id)
#   filter(capabilities) -> list[WorkerManifest]
#   health_check(worker_id) -> bool
#   list_all() -> list[WorkerManifest]
#   get(worker_id) -> WorkerManifest | None
#
# WorkerSelector:
#   select(required_capabilities, policy, privacy_tier,
#          slots_available, should_throttle) -> WorkerManifest
#
#   Decision tree (SDD 5.5):
#   1. Privacy check  -- LOCAL_ONLY hard blocks cloud
#   2. Concurrency    -- exclude OLLAMA_CLOUD if slots_available == 0
#   3. Budget         -- penalize usage_level 3-4 when should_throttle
#   4. Capability     -- filter by required_capabilities
#   5. Policy rank    -- COST_OPTIMIZED / CAPABILITY_FIRST / SPEED_OPTIMIZED
#                        / HYBRID / PRIVATE