"""
tasker.modes.cowork
--------------------
COWORK mode -- Claude Cowork analog.
Full plan/checkpoint loop. TRINITY-lite orchestration.
Routing: HYBRID. Interaction: async + checkpoint events, resumable.
Memory: project + episodic (MindSeed-compatible).
See SDD Section 5.1 and 7.5a.
"""
from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass

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


# --------------------------------------------------------------------------- #
# Runner event contract (SDD 7.5a)
# --------------------------------------------------------------------------- #

@dataclass(frozen=True)
class StepStarted:
    step_index: int
    description: str


@dataclass(frozen=True)
class StepCompleted:
    step_index: int
    output: str


@dataclass(frozen=True)
class SynthesisDelta:
    content: str


@dataclass(frozen=True)
class Paused:
    checkpoint_id: str


@dataclass(frozen=True)
class Done:
    result: str | None


RunnerEvent = StepStarted | StepCompleted | SynthesisDelta | Paused | Done


_SynthesizeFn = Callable[[str, list[dict]], Awaitable[str]]
_SynthesizeStreamFn = Callable[[str, list[dict]], AsyncIterator[str]]


def _sentence_chunks(text: str) -> list[str]:
    """
    Split *text* on sentence boundaries for the sentence-chunking synthesis
    fallback documented in SDD 7.5a. Keeps the trailing punctuation with each
    chunk so the split is reversible by concatenation.
    """
    if not text:
        return [""] if text == "" else []
    # Split after [.!?] followed by whitespace or end-of-string, using
    # lookbehind to keep the delimiter attached to the preceding sentence.
    chunks = [s.strip() for s in re.split(r"(?<=[.!?])(?=\s+|$)", text) if s.strip()]
    return chunks or [text]


class CoworkRunner:
    """
    Drives a multi-step ExecutionPlan through the session lifecycle.

    Calls SessionManager.tick() before every step. On a PAUSE directive,
    snapshots the in-progress plan into a Checkpoint and calls
    SessionManager.pause(), then yields Paused(...) from astream().

    The orchestrator and worker dispatch live outside this class (Phase 6).
    This runner owns only the session management boundary -- when to continue,
    when to stop and checkpoint.

    astream() is the primary execution path (SDD 7.5a). run() is a thin
    collector over astream() that preserves the historical str | None return
    contract.

    _step_fn: optional async (PlanStep) -> str coroutine injected by tests to
    control per-step behaviour (e.g. simulate budget exhaustion mid-plan).
    Production code leaves it None and the runner emits a stub string until
    Phase 6 wires in real worker dispatch.

    _synthesize_fn / _synthesize_stream_fn: optional callbacks that turn the
    runner's completed step records into a final answer. When absent, run()
    falls back to joining step outputs with newlines, keeping existing run()-
    level tests unchanged.
    """

    def __init__(
        self,
        mode: TaskerMode,
        session_mgr: SessionManager,
        store: CheckpointStore,
        hardware_profile: str = "unknown",
        *,
        episodic_bridge: EpisodicMemoryBridge | None = None,
        _step_fn: Callable[[PlanStep], Awaitable[str]] | None = None,
        _synthesize_fn: _SynthesizeFn | None = None,
        _synthesize_stream_fn: _SynthesizeStreamFn | None = None,
    ) -> None:
        self._mode    = mode
        self._mgr     = session_mgr
        self._store   = store
        self._profile = hardware_profile
        self._bridge  = episodic_bridge or NullEpisodicMemoryBridge()
        self._step_fn = _step_fn
        self._synthesize_fn = _synthesize_fn
        self._synthesize_stream_fn = _synthesize_stream_fn

    async def astream(
        self,
        task: str,
        plan: ExecutionPlan,
    ) -> AsyncIterator[RunnerEvent]:
        """
        Iterate over plan steps, checking the session budget before each one.

        Yields StepStarted/StepCompleted for each executed step. If the session
        must pause, writes a Checkpoint, yields Paused(checkpoint_id), and
        stops. After all steps complete, runs synthesis and yields
        SynthesisDelta events followed by Done(result).
        """
        outputs: list[str] = []
        completed: list[dict] = []
        episodic_pos: int = 0

        for step in plan.steps:
            directive = self._mgr.tick()

            if directive in (SessionDirective.PAUSE, SessionDirective.HOLD):
                cp = await self._checkpoint_and_pause(
                    task, plan, step.index, completed, episodic_pos
                )
                yield Paused(checkpoint_id=cp.id)
                return

            yield StepStarted(step_index=step.index, description=step.description)
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

            yield StepCompleted(step_index=step.index, output=output)

        # Synthesis phase ------------------------------------------------------ #
        result: str | None
        if self._synthesize_stream_fn is not None:
            chunks: list[str] = []
            async for chunk in self._synthesize_stream_fn(task, completed):
                chunks.append(chunk)
                yield SynthesisDelta(content=chunk)
            result = "".join(chunks)
        elif self._synthesize_fn is not None:
            synthesized = await self._synthesize_fn(task, completed)
            for sentence in _sentence_chunks(synthesized):
                yield SynthesisDelta(content=sentence)
            result = synthesized
        else:
            # Backward-compatible path: no synthesizer wired, return joined
            # step outputs exactly as run() did before astream() existed.
            result = "\n".join(outputs)
            yield SynthesisDelta(content=result)

        yield Done(result=result)

    async def run(self, task: str, plan: ExecutionPlan) -> str | None:
        """
        Thin collector over astream().

        Returns the synthesized output string when all steps complete, or
        None when the session must pause (checkpoint written, state = PAUSED).
        completed_steps accumulates dict records of each finished step and is
        embedded in the Checkpoint so resume can reconstruct prior results.
        """
        result: str | None = None
        async for event in self.astream(task, plan):
            if isinstance(event, Done):
                result = event.result
        return result

    async def _checkpoint_and_pause(
        self,
        task: str,
        plan: ExecutionPlan,
        current_index: int,
        completed: list[dict],
        episodic_log_position: int = 0,
    ) -> Checkpoint:
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
        return cp
