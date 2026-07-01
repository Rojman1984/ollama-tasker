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
  tier_max >= 3     → Tier 3 (ReasoningOrchestrator)

Tier 4 (CloudOrchestrator) is wired by callers that explicitly register a
cloud provider and pass tier_max >= 4.  The factory itself does not resolve
cloud worker selection.
"""
from __future__ import annotations

import uuid
from collections.abc import Awaitable, Callable

from tasker.modes.base import ExecutionConfig
from tasker.orchestrator.base import OrchestratorBase
from tasker.orchestrator.tier0_rules import NanoOrchestrator
from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
from tasker.orchestrator.tier2_dual import DualLLMOrchestrator
from tasker.orchestrator.tier3_reasoning import ReasoningOrchestrator
from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    LatencyClass,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    ToolProtocol,
    WorkerManifest,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase

_ModelCall = Callable[[str, str], Awaitable[str]]


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


def _make_call_model(
    provider: WorkerProviderBase,
    manifest: WorkerManifest,
    privacy_tier: PrivacyTier = PrivacyTier.LOCAL_ONLY,
) -> _ModelCall:
    """Wrap provider.execute() as a (system_prompt, user_prompt) -> str coroutine.
    privacy_tier must be OLLAMA_CLOUD_OK (not the narrower default
    LOCAL_ONLY) for an OLLAMA_CLOUD-routed manifest, or the call would be
    hard-blocked by the project's own privacy-tier enforcement (SDD 11.1)
    despite the provider itself supporting the cloud call."""
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
            timeout_s=120.0,
        )
        result = await provider.execute(task, manifest)
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
    call_model = _make_call_model(ollama_provider, manifest, privacy_tier)

    if tier == 1:
        return SingleLLMOrchestrator(model_id, call_model)

    if tier == 2:
        return DualLLMOrchestrator(model_id, model_id, call_model, call_model)

    # tier >= 3
    return ReasoningOrchestrator(model_id, call_model)
