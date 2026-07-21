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

from collections.abc import AsyncIterator, Awaitable, Callable

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
_ModelCallStream = Callable[[str, str], AsyncIterator[str]]


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
        mode_name: str | None = None,
        _call_model_stream: _ModelCallStream | None = None,
    ) -> None:
        self._model_id = model_id
        self._call_model = call_model
        self._call_model_stream = _call_model_stream
        self._mode_name = mode_name
        self._fallback = NanoOrchestrator()

    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        user_prompt = build_plan_prompt(task, classifier_output, available_workers, self._mode_name)
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
        prompt = build_synthesize_prompt(original_task, results, self._mode_name)
        return await self._call_model(_SYNTHESIZE_SYSTEM, prompt)

    async def synthesize_stream(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> AsyncIterator[str]:
        """Stream synthesis token deltas when a streaming callable is wired."""
        if self._call_model_stream is None:
            async for chunk in super().synthesize_stream(original_task, results):
                yield chunk
            return
        prompt = build_synthesize_prompt(original_task, results, self._mode_name)
        async for chunk in self._call_model_stream(_SYNTHESIZE_SYSTEM, prompt):
            yield chunk

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
