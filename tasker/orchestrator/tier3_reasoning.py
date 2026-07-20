"""
tasker.orchestrator.tier3_reasoning
-------------------------------------
ReasoningOrchestrator (Tier 3).
Full reasoning model as resident planner. Parallel workers.
Target: GPU server or future hardware upgrade.

Distinct from Tier 1: Tier 1 targets small models (qwen3:1.7b /
llama3.2:3b) loaded sequentially on a CPU-only machine.  Tier 3
targets large reasoning models (qwen3:30b-a3b, deepseek-r1:32b)
that stay GPU-resident across all orchestration calls — plan,
retry-decision, and synthesis all flow through the same model
without unload/reload cycles.  The class is intentionally
structurally similar to SingleLLMOrchestrator; the distinction is
the hardware target, model size, and resident-load strategy.
See SDD Section 5.3.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from tasker.orchestrator._parse import (
    PLAN_SYSTEM,
    RETRY_SYSTEM,
    SYNTHESIZE_SYSTEM,
    build_plan_prompt,
    build_retry_prompt,
    build_synthesize_prompt,
    plan_with_repair,
    parse_retry,
)
from tasker.orchestrator.base import OrchestratorBase
from tasker.orchestrator.tier0_rules import NanoOrchestrator
from tasker.workers.base import (
    ClassifierResult,
    ExecutionPlan,
    RetryDecision,
    WorkerManifest,
    WorkerResult,
)

_ModelCall = Callable[[str, str], Awaitable[str]]


class ReasoningOrchestrator(OrchestratorBase):
    """
    Tier 3: one large reasoning model, GPU-resident across all calls.

    call_model — coroutine (system_prompt, user_prompt) -> str.
    Production binds a large reasoning-capable model (qwen3:30b-a3b,
    deepseek-r1:32b).  Inject a mock in tests.
    Falls back to NanoOrchestrator on JSON parse errors.
    """

    def __init__(
        self,
        model_id: str,
        call_model: _ModelCall,
        mode_name: str | None = None,
    ) -> None:
        self._model_id  = model_id
        self._call_model = call_model
        self._mode_name  = mode_name
        self._fallback   = NanoOrchestrator()

    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        user_prompt = build_plan_prompt(task, classifier_output, available_workers, self._mode_name)
        raw = await self._call_model(PLAN_SYSTEM, user_prompt)
        result = await plan_with_repair(task, raw, self._call_model, PLAN_SYSTEM, user_prompt)
        if result is None:
            result = await self._fallback.plan(task, classifier_output, available_workers)
            result.used_fallback = True
        return result

    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> str:
        prompt = build_synthesize_prompt(original_task, results, self._mode_name)
        return await self._call_model(SYNTHESIZE_SYSTEM, prompt)

    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        raw = await self._call_model(RETRY_SYSTEM, build_retry_prompt(plan, failed_step))
        decision = parse_retry(raw)
        if decision is None:
            return RetryDecision(
                should_retry=False,
                reassign=False,
                reason="ReasoningOrchestrator: could not parse retry decision.",
            )
        return decision
