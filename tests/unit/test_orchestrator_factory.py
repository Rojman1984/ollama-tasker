"""
Unit tests -- orchestrator factory (tasker/orchestrator/factory.py)
"""
import unittest
from datetime import datetime, timezone
from unittest.mock import AsyncMock

from tasker.modes.base import ExecutionConfig, HardwareProfile, ModeConfigurator, TaskerMode
from tasker.orchestrator.factory import build_orchestrator
from tasker.orchestrator.tier0_rules import NanoOrchestrator
from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
from tasker.orchestrator.tier2_dual import DualLLMOrchestrator
from tasker.orchestrator.tier3_reasoning import ReasoningOrchestrator
from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    LatencyClass,
    MemoryScope,
    OllamaPlan,
    OllamaUsageLevel,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    ToolID,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    ModelUsage,
    WorkerStatus,
)
from tasker.workers.providers.base import WorkerProviderBase


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #

def _profile(
    tier_max: int = 1,
    model: str = "qwen3:1.7b",
    compute_location: str = "local",
) -> HardwareProfile:
    return HardwareProfile(
        name="test",
        description="test profile",
        orchestrator_tier_max=tier_max,
        orchestrator_model=model,
        orchestrator_compute_location=compute_location,
        ollama_plan=OllamaPlan.PRO,
        max_concurrent_local=1,
        max_concurrent_ollama_cloud=1,
        unload_between_tasks=True,
        ollama_base_url="http://localhost:11434",
        session_throttle_at=0.9,
        weekly_throttle_at=0.85,
        mode_constraints={},
    )


def _mode(tier_max: int = 1) -> TaskerMode:
    return TaskerMode(
        name="chat",
        orchestrator_tier_max=tier_max,
        tool_bundle=frozenset(),
        routing_policy=RoutingPolicy.PRIVATE,
        interaction_pattern=InteractionPattern.CLI_REPL,
        memory_scope=MemoryScope.SESSION,
        worker_preference_order=[ComputeLocation.LOCAL_HARDWARE],
        private_hard_block=False,
        privacy_tier=PrivacyTier.LOCAL_ONLY,
    )


def _config(
    profile_tier: int = 1,
    mode_tier: int = 1,
    compute_location: str = "local",
) -> ExecutionConfig:
    profile = _profile(profile_tier, compute_location=compute_location)
    mode = _mode(mode_tier)
    return ExecutionConfig(
        mode=mode,
        profile=profile,
        effective_tier_max=min(profile_tier, mode_tier),
        cowork_behavior="sequential_only",
        research_behavior="single_worker",
    )


class _FakeProvider(WorkerProviderBase):
    def __init__(self) -> None:
        self.calls: list[tuple] = []

    def supports(self, worker: WorkerManifest) -> bool:
        return True

    async def health_check(self, worker: WorkerManifest) -> bool:
        return True

    async def execute(self, task, worker: WorkerManifest) -> WorkerResult:
        self.calls.append((task, worker))
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=WorkerStatus.SUCCESS,
            output='{"plan_id":"p1","steps":[{"index":0,"description":"step","role":"worker","required_capabilities":["tool_use"],"depends_on":[]}],"dependency_graph":{"0":[]}}',
            tool_results=[],
            usage=ModelUsage(0, 0, 0.0),
            duration_ms=10,
        )


# --------------------------------------------------------------------------- #
# Tier selection tests
# --------------------------------------------------------------------------- #

class TestBuildOrchestratorTierSelection(unittest.TestCase):

    def test_tier0_returns_nano(self):
        config = _config(profile_tier=0, mode_tier=0)
        result = build_orchestrator(config, {})
        self.assertIsInstance(result, NanoOrchestrator)

    def test_tier0_even_with_provider_registered(self):
        config = _config(profile_tier=0, mode_tier=0)
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, NanoOrchestrator)

    def test_tier1_with_ollama_provider(self):
        config = _config(profile_tier=1, mode_tier=1)
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, SingleLLMOrchestrator)

    def test_tier2_with_ollama_provider(self):
        config = _config(profile_tier=2, mode_tier=2)
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, DualLLMOrchestrator)

    def test_tier3_with_ollama_provider(self):
        config = _config(profile_tier=3, mode_tier=3)
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, ReasoningOrchestrator)

    def test_tier4_falls_back_to_reasoning(self):
        config = _config(profile_tier=4, mode_tier=4)
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, ReasoningOrchestrator)

    def test_no_ollama_provider_falls_back_to_nano(self):
        config = _config(profile_tier=1, mode_tier=1)
        result = build_orchestrator(config, {})
        self.assertIsInstance(result, NanoOrchestrator)

    def test_profile_tier_caps_mode_tier(self):
        # profile tier_max=1 caps even if mode allows tier 3
        config = _config(profile_tier=1, mode_tier=3)
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, SingleLLMOrchestrator)

    def test_model_id_propagates_to_tier1(self):
        config = ExecutionConfig(
            mode=_mode(1),
            profile=_profile(1, "llama3.2:3b"),
            effective_tier_max=1,
            cowork_behavior="sequential_only",
            research_behavior="single_worker",
        )
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, SingleLLMOrchestrator)
        self.assertEqual(result._model_id, "llama3.2:3b")


# --------------------------------------------------------------------------- #
# Call model wiring
# --------------------------------------------------------------------------- #

class TestCallModelWiring(unittest.IsolatedAsyncioTestCase):

    async def test_call_model_invokes_provider_execute(self):
        fake = _FakeProvider()
        config = _config(profile_tier=1, mode_tier=1)
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: fake})
        self.assertIsInstance(orchestrator, SingleLLMOrchestrator)

        # Calling the internal _call_model should reach fake.execute()
        await orchestrator._call_model("system msg", "user msg")
        self.assertEqual(len(fake.calls), 1)
        task, worker = fake.calls[0]
        self.assertEqual(task.instruction, "user msg")
        self.assertEqual(task.context.get("system_prompt"), "system msg")

    async def test_call_model_uses_orchestrator_model_id(self):
        fake = _FakeProvider()
        config = ExecutionConfig(
            mode=_mode(1),
            profile=_profile(1, "deepseek-r1:7b"),
            effective_tier_max=1,
            cowork_behavior="sequential_only",
            research_behavior="single_worker",
        )
        build_orchestrator(config, {ProviderType.OLLAMA: fake})
        # Manifest passed to execute should have the configured model_id
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: fake})
        await orchestrator._call_model("sys", "usr")
        _, worker = fake.calls[-1]
        self.assertEqual(worker.model_id, "deepseek-r1:7b")

    async def test_provider_failure_returns_empty_string(self):
        """Provider exception should propagate (no silent swallow in call_model)."""
        class _BrokenProvider(_FakeProvider):
            async def execute(self, task, worker):
                raise RuntimeError("network down")

        config = _config(1, 1)
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: _BrokenProvider()})
        with self.assertRaises(RuntimeError):
            await orchestrator._call_model("sys", "usr")


# --------------------------------------------------------------------------- #
# Ollama-Cloud-routed orchestrator (planner) model
# --------------------------------------------------------------------------- #

class TestBuildOrchestratorCloudRouting(unittest.IsolatedAsyncioTestCase):

    async def test_local_default_behaves_as_before(self):
        """Regression: orchestrator_compute_location='local' (the default)
        must produce identical manifest wiring to today's behavior."""
        fake = _FakeProvider()
        config = _config(profile_tier=1, mode_tier=1, compute_location="local")
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: fake})
        self.assertIsInstance(orchestrator, SingleLLMOrchestrator)
        await orchestrator._call_model("sys", "usr")
        task, worker = fake.calls[-1]
        self.assertEqual(worker.compute_location, ComputeLocation.LOCAL_HARDWARE)
        self.assertEqual(task.privacy_tier, PrivacyTier.LOCAL_ONLY)

    async def test_ollama_cloud_routes_manifest_and_privacy_tier(self):
        fake = _FakeProvider()
        config = _config(profile_tier=1, mode_tier=1, compute_location="ollama_cloud")
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: fake})
        self.assertIsInstance(orchestrator, SingleLLMOrchestrator)
        await orchestrator._call_model("sys", "usr")
        task, worker = fake.calls[-1]
        self.assertEqual(worker.compute_location, ComputeLocation.OLLAMA_CLOUD)
        self.assertEqual(task.privacy_tier, PrivacyTier.OLLAMA_CLOUD_OK)

    def test_ollama_cloud_still_resolves_ollama_provider_type(self):
        """No new provider type needed -- cloud routing still only ever
        needs provider_registry[ProviderType.OLLAMA]."""
        config = _config(profile_tier=1, mode_tier=1, compute_location="ollama_cloud")
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, SingleLLMOrchestrator)

    def test_ollama_cloud_without_ollama_provider_falls_back_to_nano(self):
        config = _config(profile_tier=1, mode_tier=1, compute_location="ollama_cloud")
        result = build_orchestrator(config, {})
        self.assertIsInstance(result, NanoOrchestrator)


if __name__ == "__main__":
    unittest.main()
