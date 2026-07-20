"""
tasker.orchestrator.tier1_single
----------------------------------
SingleLLMOrchestrator (Tier 1).
One small model, role-switched via system prompt.
Sequential load: load -> plan -> unload -> worker runs.
Target: TASKER-P1 normal operation (qwen3:1.7b or llama3.2:3b).
See SDD Section 5.3.
"""
from __future__ import annotations

from collections.abc import Awaitable, Callable

from tasker.orchestrator._parse import (
    PLAN_SYSTEM as _PLAN_SYSTEM,
    RETRY_SYSTEM as _RETRY_SYSTEM,
    SYNTHESIZE_SYSTEM as _SYNTHESIZE_SYSTEM,
    build_plan_prompt,
    build_retry_prompt,
    build_synthesize_prompt,
    plan_with_repair as _plan_with_repair,
    parse_retry as _parse_retry,
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

_ModelCall = Callable[[str, str], Awaitable[str]]   # (system_prompt, user_prompt) -> response


class SingleLLMOrchestrator(OrchestratorBase):
    """
    Tier 1: one small orchestrator model, sequential load strategy.

    call_model is a coroutine (system_prompt, user_prompt) -> str.
    Inject a mock in tests; production wires in OllamaProvider.generate().
    Falls back to NanoOrchestrator behaviour on JSON parse errors.
    """

    def __init__(
        self,
        model_id: str,
        call_model: _ModelCall,
    ) -> None:
        self._model_id = model_id
        self._call_model = call_model
        self._fallback = NanoOrchestrator()

    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        user_prompt = build_plan_prompt(task, classifier_output, available_workers)
        raw = await self._call_model(_PLAN_SYSTEM, user_prompt)
        plan = await _plan_with_repair(task, raw, self._call_model, _PLAN_SYSTEM, user_prompt)
        if plan is None:
            # _plan_with_repair already tried a tolerant text repair and one
            # re-ask, logging a WARNING with the raw response -- here we
            # just mark the resulting plan so callers/tests can tell "the
            # model's real plan" apart from "the generic Nano template".
            plan = await self._fallback.plan(task, classifier_output, available_workers)
            plan.used_fallback = True
        return plan

    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> str:
        return await self._call_model(_SYNTHESIZE_SYSTEM, build_synthesize_prompt(original_task, results))

    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        raw = await self._call_model(_RETRY_SYSTEM, build_retry_prompt(plan, failed_step))
        decision = _parse_retry(raw)
        if decision is None:
            return RetryDecision(
                should_retry=False,
                reassign=False,
                reason="SingleLLMOrchestrator: could not parse retry decision.",
            )
        return decision
