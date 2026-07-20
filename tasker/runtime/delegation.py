"""
tasker.runtime.delegation
---------------------------
DELEGATE_AGENT sub-task dispatch context (SDD 5.7c).

Carries what a delegated sub-task must INHERIT rather than bypass: the
exact same pipeline tuple (budget, concurrency manager, provider map,
orchestrator) the parent task is using, so a sub-agent consumes the
parent's own Ollama Cloud concurrency slots and session budget -- never
its own separate allowance -- plus the recursion-safety counters
(depth, total sub-agents spawned for this whole top-level task) that
keep delegation bounded.

A leaf module deliberately: tasker/tools/executor.py imports this
directly, but never tasker/runtime/dispatch.py itself (that import is
local/deferred inside _exec_delegate_agent to avoid a real import cycle
-- dispatch.py -> tasker.tools.loop -> tasker.tools.executor already
exists in the other direction).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from tasker.session.checkpoint import CheckpointStore
    from tasker.workers.registry import WorkerRegistry

# SDD 5.7c: bounded depth and per-task cap, not configurable per-call --
# a worker requesting delegate_agent cannot raise its own ceiling.
DEFAULT_MAX_DEPTH = 2
DEFAULT_MAX_SUB_AGENTS = 3


@dataclass
class DelegationContext:
    registry: "WorkerRegistry"
    store: "CheckpointStore"
    mode_name: str
    pipeline: tuple
    depth: int = 0
    # A single-element list, not an int, so child() can share the SAME
    # counter object across the whole delegation tree -- the cap is per
    # top-level task, not reset per delegation level. Safe without a lock:
    # asyncio is cooperative and _exec_delegate_agent's check-then-increment
    # has no `await` between them, so no other coroutine can interleave.
    spawned: list[int] = field(default_factory=lambda: [0])
    max_depth: int = DEFAULT_MAX_DEPTH
    max_sub_agents: int = DEFAULT_MAX_SUB_AGENTS

    def child(self) -> "DelegationContext":
        """The delegation context a spawned sub-task runs with: one level
        deeper, same registry/store/mode/pipeline/spawned-counter/limits."""
        return DelegationContext(
            registry=self.registry,
            store=self.store,
            mode_name=self.mode_name,
            pipeline=self.pipeline,
            depth=self.depth + 1,
            spawned=self.spawned,
            max_depth=self.max_depth,
            max_sub_agents=self.max_sub_agents,
        )
