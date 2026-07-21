"""
tasker.orchestrator.factory
-----------------------------
build_orchestrator(config, provider_registry) -> OrchestratorBase.

Selects and wires the correct orchestrator tier from a resolved ExecutionConfig.
Builds an ad-hoc WorkerManifest for the orchestrator model specified in the
hardware profile, then wraps WorkerProviderBase.execute() into the
(system_prompt, user_prompt) -> str callable required by tiers 1–3.

Fallback chain:
  no provider found → Tier 0 (NanoOrchestrator)
  tier_max == 0     → Tier 0
  tier_max == 1     → Tier 1 (SingleLLMOrchestrator)
  tier_max == 2     → Tier 2 (DualLLMOrchestrator, same model for both roles)
  tier_max == 3     → Tier 3 (ReasoningOrchestrator)
  tier_max >= 4     → Tier 4 (CloudOrchestrator) when the profile routes the
                      orchestrator model to Ollama Cloud
                      (orchestrator.compute_location: ollama_cloud);
                      otherwise degrades to Tier 3 with a WARNING
                      (SDD 5.3 "Tier 4 activation", SDD 10.3 chain).
                      Before task 8.2 the factory never constructed
                      CloudOrchestrator at all — Tier 4 was unreachable
                      from every mode x profile combination.
"""
from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Awaitable, Callable

from tasker.modes.base import ExecutionConfig
from tasker.orchestrator.base import OrchestratorBase
from tasker.orchestrator.tier0_rules import NanoOrchestrator
from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
from tasker.orchestrator.tier2_dual import DualLLMOrchestrator
from tasker.orchestrator.tier3_reasoning import ReasoningOrchestrator
from tasker.orchestrator.tier4_cloud import CloudOrchestrator
from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    LatencyClass,
    OllamaCloudConcurrencyExhaustedError,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase

logger = logging.getLogger(__name__)

_ModelCall = Callable[[str, str], Awaitable[str]]

# DEFERRED (no Ollama Cloud concurrency slot) is transient -- worth a
# short bounded wait before failing the orchestrator step outright,
# mirroring the same pattern already used for worker-level tool calls in
# tasker/tools/loop.py's _execute_with_deferred_retry().
_DEFERRED_MAX_RETRIES = 3
_DEFERRED_BACKOFF_S = 0.5


def _build_orchestrator_manifest(
    model_id: str,
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
) -> WorkerManifest:
    """Ad-hoc manifest for the orchestrator model (not in worker registry).
    compute_location=OLLAMA_CLOUD lets planning use a stronger model via
    Ollama's own cloud (e.g. gpt-oss:120b-cloud) while the worker stays
    local -- same OllamaProvider/endpoint either way, see SDD 5.6.1."""
    return WorkerManifest(
        id=f"orchestrator-{model_id}",
        provider=ProviderType.OLLAMA,
        model_id=model_id,
        compute_location=compute_location,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


async def _execute_with_deferred_retry(
    provider: WorkerProviderBase, task: WorkerTask, manifest: WorkerManifest,
) -> WorkerResult:
    """Bounded retry on DEFERRED (no concurrency slot) before giving up --
    same semantics as tasker/tools/loop.py's worker-side equivalent."""
    result: WorkerResult | None = None
    for attempt in range(_DEFERRED_MAX_RETRIES):
        result = await provider.execute(task, manifest)
        if result.status != WorkerStatus.DEFERRED:
            return result
        if attempt < _DEFERRED_MAX_RETRIES - 1:
            logger.warning(
                "build_orchestrator: %s deferred (no Ollama Cloud concurrency "
                "slot), retrying (%d/%d)",
                manifest.model_id, attempt + 1, _DEFERRED_MAX_RETRIES,
            )
            await asyncio.sleep(_DEFERRED_BACKOFF_S)
    return result


def make_call_model(
    provider: WorkerProviderBase,
    manifest: WorkerManifest,
    privacy_tier: PrivacyTier = PrivacyTier.LOCAL_ONLY,
    timeout_s: float = 240.0,
) -> _ModelCall:
    """Wrap provider.execute() as a (system_prompt, user_prompt) -> str coroutine.
    privacy_tier must be OLLAMA_CLOUD_OK (not the narrower default
    LOCAL_ONLY) for an OLLAMA_CLOUD-routed manifest, or the call would be
    hard-blocked by the project's own privacy-tier enforcement (SDD 11.1)
    despite the provider itself supporting the cloud call.

    *timeout_s* defaults to 240s because live-measured on Designlab1 against
    lfm2.5-thinking:latest, a single plan() call took 94.5s real time
    (17417-char thinking block, 3922 eval tokens) for a trivially simple
    task, and a second attempt exceeded 120s outright and raised
    TimeoutError. Callers that need a shorter bound (e.g. the research-mode
    query rewriter) can pass their own value.

    A DEFERRED result (no Ollama Cloud concurrency slot) is retried a
    bounded number of times, then raises OllamaCloudConcurrencyExhaustedError
    rather than silently collapsing into an empty string indistinguishable
    from a genuinely empty model response -- the exception propagates
    uncaught through plan()/synthesize()/should_retry() (tiers 1-3 do not
    catch exceptions from call_model), reaching callers' existing
    try/except around orchestrator calls (e.g. cli/shell.py's
    "Planning failed: ..." handler)."""
    async def call_model(system_prompt: str, user_prompt: str) -> str:
        task = WorkerTask(
            task_id=str(uuid.uuid4()),
            step_index=0,
            role=AgentRole.THINKER,
            instruction=user_prompt,
            tools=[],
            context={"system_prompt": system_prompt},
            routing_policy=RoutingPolicy.PRIVATE,
            privacy_tier=privacy_tier,
            timeout_s=timeout_s,
        )
        result = await _execute_with_deferred_retry(provider, task, manifest)
        if result.status == WorkerStatus.DEFERRED:
            raise OllamaCloudConcurrencyExhaustedError(
                f"orchestrator call to {manifest.model_id!r} could not acquire "
                f"an Ollama Cloud concurrency slot after {_DEFERRED_MAX_RETRIES} attempts"
            )
        return result.output or ""
    return call_model


def build_orchestrator(
    config: ExecutionConfig,
    provider_registry: dict[ProviderType, WorkerProviderBase],
) -> OrchestratorBase:
    """
    Construct the correct orchestrator tier from a resolved ExecutionConfig,
    wiring its model-call callables to real WorkerProviderBase.execute() calls
    against the orchestrator model specified in the hardware profile.
    """
    tier = config.effective_tier_max
    model_id = config.profile.orchestrator_model

    if tier == 0:
        return NanoOrchestrator()

    ollama_provider = provider_registry.get(ProviderType.OLLAMA)
    if ollama_provider is None:
        return NanoOrchestrator()

    if config.profile.orchestrator_compute_location == "ollama_cloud":
        compute_location = ComputeLocation.OLLAMA_CLOUD
        privacy_tier = PrivacyTier.OLLAMA_CLOUD_OK
    else:
        compute_location = ComputeLocation.LOCAL_HARDWARE
        privacy_tier = PrivacyTier.LOCAL_ONLY

    manifest = _build_orchestrator_manifest(model_id, compute_location)
    call_model = make_call_model(ollama_provider, manifest, privacy_tier)

    # Threaded into every LLM-calling tier so plan()/synthesize() can apply
    # RESEARCH mode's grounding requirement (SDD 5.1a) to their prompts.
    mode_name = config.mode.name

    if tier == 1:
        return SingleLLMOrchestrator(model_id, call_model, mode_name=mode_name)

    if tier == 2:
        return DualLLMOrchestrator(
            model_id, model_id, call_model, call_model, mode_name=mode_name,
        )

    if tier >= 4:
        if compute_location == ComputeLocation.OLLAMA_CLOUD:
            # Tier 4: the cloud model IS the orchestrator worker. Routed
            # through provider.execute() directly (no call_model closure),
            # so the 8.1 wiring applies automatically: concurrency slots
            # and budget units are acquired/recorded per orchestration
            # call via the shared OllamaProvider instance.
            return CloudOrchestrator(
                ollama_provider, manifest, privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
                mode_name=mode_name,
            )
        logger.warning(
            "build_orchestrator: tier %d requested but the profile's "
            "orchestrator compute_location is %r -- Tier 4 requires a "
            "cloud-routed orchestrator model; degrading to Tier 3 (SDD 10.3).",
            tier, config.profile.orchestrator_compute_location,
        )

    # tier == 3, or tier >= 4 degraded above
    return ReasoningOrchestrator(model_id, call_model, mode_name=mode_name)
