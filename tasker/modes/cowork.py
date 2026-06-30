"""
tasker.modes.cowork
--------------------
COWORK mode -- Claude Cowork analog.
Full plan/checkpoint loop. TRINITY-lite orchestration.
Routing: HYBRID. Interaction: async + checkpoint events, resumable.
Memory: project + episodic (MindSeed-compatible).
See SDD Section 5.1.
"""
from __future__ import annotations

from tasker.modes.base import TaskerMode
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import Checkpoint, CheckpointStore
from tasker.session.episodic import EpisodicMemoryBridge, NullEpisodicMemoryBridge
from tasker.session.manager import SessionManager
from tasker.tools.bundles import COWORK_BUNDLE
from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    ExecutionPlan,
    InteractionPattern,
    MemoryScope,
    PlanStep,
    PrivacyTier,
    RoutingPolicy,
    SessionDirective,
    StepStatus,
    ToolID,
)

COWORK_MODE = TaskerMode(
    name="cowork",
    orchestrator_tier_max=3,
    tool_bundle=COWORK_BUNDLE,
    routing_policy=RoutingPolicy.HYBRID,
    interaction_pattern=InteractionPattern.ASYNC_CHECKPOINT,
    memory_scope=MemoryScope.PROJECT_EPISODIC,
    worker_preference_order=[
        ComputeLocation.LOCAL_HARDWARE,
        ComputeLocation.OLLAMA_CLOUD,
        ComputeLocation.DIRECT_CLOUD,
    ],
    private_hard_block=False,
    privacy_tier=PrivacyTier.ANY_CLOUD,
)


class CoworkRunner:
    """
    Drives a multi-step ExecutionPlan through the session lifecycle.

    Calls SessionManager.tick() before every step. On a PAUSE directive,
    snapshots the in-progress plan into a Checkpoint and calls
    SessionManager.pause(), then returns None to signal the halt.

    The orchestrator and worker dispatch live outside this class (Phase 6).
    This runner owns only the session management boundary — when to continue,
    when to stop and checkpoint.

    _step_fn: optional async (PlanStep) -> str coroutine injected by tests to
    control per-step behaviour (e.g. simulate budget exhaustion mid-plan).
    Production code leaves it None and the runner emits a stub string until
    Phase 6 wires in real worker dispatch.
    """

    def __init__(
        self,
        mode: TaskerMode,
        session_mgr: SessionManager,
        store: CheckpointStore,
        hardware_profile: str = "unknown",
        *,
        episodic_bridge: EpisodicMemoryBridge | None = None,
        _step_fn=None,
    ) -> None:
        self._mode    = mode
        self._mgr     = session_mgr
        self._store   = store
        self._profile = hardware_profile
        self._bridge  = episodic_bridge or NullEpisodicMemoryBridge()
        self._step_fn = _step_fn

    async def run(self, task: str, plan: ExecutionPlan) -> str | None:
        """
        Iterate over plan steps, checking the session budget before each one.

        Returns the synthesised output string when all steps complete, or
        None when the session must pause (checkpoint written, state = PAUSED).
        completed_steps accumulates dict records of each finished step and is
        embedded in the Checkpoint so resume can reconstruct prior results.
        """
        outputs: list[str] = []
        completed: list[dict] = []
        episodic_pos: int = 0

        for step in plan.steps:
            directive = self._mgr.tick()

            if directive in (SessionDirective.PAUSE, SessionDirective.HOLD):
                await self._checkpoint_and_pause(
                    task, plan, step.index, completed, episodic_pos
                )
                return None

            step.status = StepStatus.ACTIVE

            if self._step_fn is not None:
                output = await self._step_fn(step)
            else:
                output = f"[step {step.index}: {step.description}]"

            step.status = StepStatus.COMPLETED
            outputs.append(output)
            record = {"step_index": step.index, "output": output}
            completed.append(record)

            # Record step completion in episodic memory; update position
            episodic_pos = self._bridge.record_event(
                self._mgr.session_id,
                {"kind": "step_completed", **record},
            )

        return "\n".join(outputs)

    async def _checkpoint_and_pause(
        self,
        task: str,
        plan: ExecutionPlan,
        current_index: int,
        completed: list[dict],
        episodic_log_position: int = 0,
    ) -> None:
        cp = Checkpoint.new(
            mode=self._mode.name,
            hardware_profile=self._profile,
            original_task=task,
            budget_snapshot=self._mgr.budget.snapshot(),
            plan=plan,
            current_step_index=current_index,
            completed_steps=completed,
            episodic_log_position=episodic_log_position,
        )
        await self._mgr.pause(cp)
