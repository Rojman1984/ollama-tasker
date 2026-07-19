"""
tasker.orchestrator.tier4_cloud
---------------------------------
CloudOrchestrator (Tier 4).
Fugu / Claude / OpenAI as orchestrator. Local workers unchanged.

Distinct from Tiers 1-3: this tier does not use a _ModelCall callable.
Instead it routes planning and synthesis through WorkerProviderBase.execute(),
building a WorkerTask the same way worker dispatch does.  This means the
orchestrator itself is served by a cloud provider worker — Fugu, Anthropic,
or OpenAI — and benefits from their larger context windows and reasoning
capabilities without the orchestrator layer needing to know provider specifics.

LOCAL_ONLY privacy tier is rejected in the constructor because routing
orchestration through a cloud provider would violate the hard block.
See SDD Section 5.3.
"""
from __future__ import annotations

import uuid

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
    AgentRole,
    ClassifierResult,
    ExecutionPlan,
    ModelUsage,
    PrivacyTier,
    RetryDecision,
    RoutingPolicy,
    TaskerPolicyError,
    ToolDefinition,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase


class CloudOrchestrator(OrchestratorBase):
    """
    Tier 4: cloud provider acts as orchestrator worker.

    provider — a WorkerProviderBase implementation (Fugu, Anthropic, OpenAI).
    worker   — the WorkerManifest for the cloud orchestrator model.
    privacy_tier — must NOT be LOCAL_ONLY; checked at construction time.

    Falls back to NanoOrchestrator on parse errors or provider failures.
    """

    def __init__(
        self,
        provider: WorkerProviderBase,
        worker: WorkerManifest,
        privacy_tier: PrivacyTier = PrivacyTier.ANY_CLOUD,
    ) -> None:
        if privacy_tier == PrivacyTier.LOCAL_ONLY:
            raise TaskerPolicyError(
                "CloudOrchestrator cannot be used with PrivacyTier.LOCAL_ONLY — "
                "it routes orchestration calls through a cloud provider."
            )
        self._provider     = provider
        self._worker       = worker
        self._privacy_tier = privacy_tier
        self._fallback     = NanoOrchestrator()

    # ------------------------------------------------------------------ #
    # Internal helper
    # ------------------------------------------------------------------ #

    def _make_task(self, instruction: str, step_index: int = 0) -> WorkerTask:
        return WorkerTask(
            task_id=str(uuid.uuid4()),
            step_index=step_index,
            role=AgentRole.THINKER,
            instruction=instruction,
            tools=[],
            context={},
            routing_policy=RoutingPolicy.CAPABILITY_FIRST,
            privacy_tier=self._privacy_tier,
        )

    async def _call(self, system_prompt: str, user_prompt: str) -> str | None:
        """Route a (system, user) call through the provider. Returns output or None."""
        full_instruction = f"{system_prompt}\n\n{user_prompt}"
        task = self._make_task(full_instruction)
        result = await self._provider.execute(task, self._worker)
        if result.status == WorkerStatus.SUCCESS and result.output:
            return result.output
        return None

    # ------------------------------------------------------------------ #
    # OrchestratorBase interface
    # ------------------------------------------------------------------ #

    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        raw = await self._call(PLAN_SYSTEM, build_plan_prompt(task, classifier_output, available_workers))
        result = parse_plan(task, raw or "") if raw else None
        if result is None:
            result = await self._fallback.plan(task, classifier_output, available_workers)
            result.used_fallback = True
        return result

    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> str:
        raw = await self._call(SYNTHESIZE_SYSTEM, build_synthesize_prompt(original_task, results))
        return raw or "(synthesis unavailable)"

    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        raw = await self._call(RETRY_SYSTEM, build_retry_prompt(plan, failed_step))
        decision = parse_retry(raw or "") if raw else None
        if decision is None:
            return RetryDecision(
                should_retry=False,
                reassign=False,
                reason="CloudOrchestrator: could not parse retry decision.",
            )
        return decision
