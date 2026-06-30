"""
tasker.modes.code
------------------
CODE mode -- Claude Code analog.
Tools: bash, file_read, file_write, git, linter, test_runner, code_search.
Routing: CAPABILITY_FIRST (coding specialists preferred).
Interaction: CLI/REPL + diffs, await approval on destructive ops.
See SDD Section 5.1.
"""
from __future__ import annotations

from tasker.modes.base import TaskerMode
from tasker.tools.bundles import CODE_BUNDLE
from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    MemoryScope,
    PrivacyTier,
    RoutingPolicy,
)

CODE_MODE = TaskerMode(
    name="code",
    orchestrator_tier_max=1,
    tool_bundle=CODE_BUNDLE,
    routing_policy=RoutingPolicy.CAPABILITY_FIRST,
    interaction_pattern=InteractionPattern.CLI_REPL,
    memory_scope=MemoryScope.PROJECT_AWARE,
    worker_preference_order=[
        ComputeLocation.LOCAL_HARDWARE,
        ComputeLocation.OLLAMA_CLOUD,
        ComputeLocation.DIRECT_CLOUD,
    ],
    private_hard_block=False,
    privacy_tier=PrivacyTier.ANY_CLOUD,
)
