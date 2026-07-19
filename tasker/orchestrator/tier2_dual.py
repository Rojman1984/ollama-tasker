"""
tasker.orchestrator.tier2_dual
--------------------------------
DualLLMOrchestrator (Tier 2).
Separate resident planner + synthesizer models. Workers hot-swap.
Target: Designlab1 with GTX 1050 Ti (can keep two small models in VRAM).

Distinct from Tier 1: Tier 1 role-switches a single model via system
prompt, unloading between plan and synthesize.  Tier 2 keeps a dedicated
planner model resident for planning/retry decisions and a dedicated
synthesizer model resident for output assembly — enabling overlapped
GPU memory use on hardware with enough VRAM for two small models.
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
    parse_plan,
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


class DualLLMOrchestrator(OrchestratorBase):
    """
    Tier 2: two resident models — one for planning/retry, one for synthesis.

    call_planner  — coroutine (system_prompt, user_prompt) -> str, used for
                    plan() and should_retry() calls.
    call_synthesizer — coroutine (system_prompt, user_prompt) -> str, used
                       for synthesize() calls only.

    Inject mocks in tests; production wires in two OllamaProvider.generate()
    coroutines bound to different model IDs.
    Falls back to NanoOrchestrator on JSON parse errors.
    """

    def __init__(
        self,
        planner_model_id: str,
        synthesizer_model_id: str,
        call_planner: _ModelCall,
        call_synthesizer: _ModelCall,
    ) -> None:
        self._planner_id      = planner_model_id
        self._synthesizer_id  = synthesizer_model_id
        self._call_planner    = call_planner
        self._call_synthesizer = call_synthesizer
        self._fallback         = NanoOrchestrator()

    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        raw = await self._call_planner(PLAN_SYSTEM, build_plan_prompt(task, classifier_output, available_workers))
        result = parse_plan(task, raw)
        if result is None:
            result = await self._fallback.plan(task, classifier_output, available_workers)
            result.used_fallback = True
        return result

    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> str:
        return await self._call_synthesizer(SYNTHESIZE_SYSTEM, build_synthesize_prompt(original_task, results))

    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        raw = await self._call_planner(RETRY_SYSTEM, build_retry_prompt(plan, failed_step))
        decision = parse_retry(raw)
        if decision is None:
            return RetryDecision(
                should_retry=False,
                reassign=False,
                reason="DualLLMOrchestrator: could not parse retry decision.",
            )
        return decision
