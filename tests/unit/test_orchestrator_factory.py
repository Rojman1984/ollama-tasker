"""
Unit tests -- orchestrator factory (tasker/orchestrator/factory.py)
"""
import unittest
from datetime import datetime, timezone
from unittest import mock
from unittest.mock import AsyncMock

from tasker.modes.base import ExecutionConfig, HardwareProfile, ModeConfigurator, TaskerMode
from tasker.orchestrator.factory import build_orchestrator
from tasker.orchestrator.tier0_rules import NanoOrchestrator
from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
from tasker.orchestrator.tier2_dual import DualLLMOrchestrator
from tasker.orchestrator.tier3_reasoning import ReasoningOrchestrator
from tasker.orchestrator.tier4_cloud import CloudOrchestrator
from tasker.workers.base import (
    ComputeLocation,
    InteractionPattern,
    LatencyClass,
    MemoryScope,
    OllamaCloudConcurrencyExhaustedError,
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
from tasker.workers.providers.ollama import OllamaProvider


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

    def test_tier4_with_cloud_orchestrator_location_returns_cloud(self):
        # Task 8.2: tier >= 4 + orchestrator routed to Ollama Cloud
        # constructs CloudOrchestrator (previously never constructed at all).
        config = _config(profile_tier=4, mode_tier=4, compute_location="ollama_cloud")
        result = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        self.assertIsInstance(result, CloudOrchestrator)

    def test_tier4_with_local_orchestrator_degrades_to_reasoning(self):
        # Tier 4 requires a cloud-routed orchestrator model; a local
        # compute_location degrades to Tier 3 per SDD 10.3 (was the
        # unconditional behavior before task 8.2).
        config = _config(profile_tier=4, mode_tier=4, compute_location="local")
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


# --------------------------------------------------------------------------- #
# Concurrency slot-limiting for cloud orchestrator calls
# --------------------------------------------------------------------------- #

class _ScriptedConcurrencyManager:
    """
    Returns a scripted sequence of try_acquire() results -- lets tests drive
    OllamaProvider's DEFERRED retry path deterministically, without
    depending on a real OllamaCloudConcurrencyManager's timing/slot count.
    Mirrors the real manager's interface (see tests/unit/test_concurrency_
    manager.py for the real thing's behavior in isolation).
    """
    def __init__(self, acquire_results: list[bool]):
        self._results = list(acquire_results)
        self.acquire_calls = 0
        self.release_calls = 0

    async def try_acquire(self) -> bool:
        result = self._results[min(self.acquire_calls, len(self._results) - 1)]
        self.acquire_calls += 1
        return result

    async def release(self) -> None:
        self.release_calls += 1


def _ollama_post_ok(content: str = "response text"):
    async def _post(url: str, payload: dict) -> tuple[int, dict]:
        payload.pop("_timeout", None)
        return 200, {
            "message": {"role": "assistant", "content": content},
            "prompt_eval_count": 10,
            "eval_count": 5,
            "done": True,
        }
    return _post


class TestOrchestratorCloudConcurrency(unittest.IsolatedAsyncioTestCase):
    """
    Regression coverage: previously, no code path in this project ever
    constructed an OllamaCloudConcurrencyManager, so OLLAMA_CLOUD-routed
    orchestrator calls proceeded without any slot-limiting even though
    OllamaProvider.execute() already had the gating logic built in --
    the gate just never got wired to anything. Uses the real
    OllamaProvider (HTTP mocked) so the actual gating code path is
    exercised, not a re-implementation of it.
    """

    async def test_call_model_retries_on_deferred_then_succeeds(self):
        mgr = _ScriptedConcurrencyManager([False, False, True])
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            concurrency_mgr=mgr,
            _post_fn=_ollama_post_ok("recovered plan"),
        )
        config = _config(profile_tier=1, mode_tier=1, compute_location="ollama_cloud")
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: provider})
        with mock.patch("tasker.orchestrator.factory._DEFERRED_BACKOFF_S", 0.001):
            output = await orchestrator._call_model("sys", "usr")
        self.assertEqual(output, "recovered plan")
        self.assertEqual(mgr.acquire_calls, 3)

    async def test_call_model_raises_after_exhausting_deferred_retries(self):
        """Must NOT silently proceed without a slot -- this is the actual bug."""
        mgr = _ScriptedConcurrencyManager([False, False, False])
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            concurrency_mgr=mgr,
            _post_fn=_ollama_post_ok("should never be reached"),
        )
        config = _config(profile_tier=1, mode_tier=1, compute_location="ollama_cloud")
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: provider})
        with mock.patch("tasker.orchestrator.factory._DEFERRED_BACKOFF_S", 0.001):
            with self.assertRaises(OllamaCloudConcurrencyExhaustedError):
                await orchestrator._call_model("sys", "usr")
        self.assertEqual(mgr.acquire_calls, 3)  # _DEFERRED_MAX_RETRIES, no more

    async def test_call_model_does_not_retry_when_slot_immediately_available(self):
        mgr = _ScriptedConcurrencyManager([True])
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            concurrency_mgr=mgr,
            _post_fn=_ollama_post_ok("first try"),
        )
        config = _config(profile_tier=1, mode_tier=1, compute_location="ollama_cloud")
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: provider})
        output = await orchestrator._call_model("sys", "usr")
        self.assertEqual(output, "first try")
        self.assertEqual(mgr.acquire_calls, 1)

    async def test_local_compute_location_never_gated_by_concurrency(self):
        """LOCAL_HARDWARE-routed orchestrator calls must never even check
        the concurrency manager -- OllamaProvider's is_cloud gate already
        handles this; guards against that regressing."""
        mgr = _ScriptedConcurrencyManager([False])  # would always defer if ever checked
        provider = OllamaProvider(
            base_url="http://localhost:11434",
            concurrency_mgr=mgr,
            _post_fn=_ollama_post_ok("local response"),
        )
        config = _config(profile_tier=1, mode_tier=1, compute_location="local")
        orchestrator = build_orchestrator(config, {ProviderType.OLLAMA: provider})
        output = await orchestrator._call_model("sys", "usr")
        self.assertEqual(output, "local response")
        self.assertEqual(mgr.acquire_calls, 0)


class TestTier4Reachability(unittest.TestCase):
    """
    Task 8.2 regression: tier resolution from the REAL shipped YAML configs.

    Tier 4 is deliberately unreachable from the standard machine profiles
    (hardware tier ceiling: min() caps at 2 on Designlab1, 1 on TASKER-P1)
    and reachable only via the explicit tier4_cloud_hybrid opt-in profile
    with COWORK mode (the only mode whose orchestrator_tier_max is 4).
    See SDD 5.3 "Tier 4 activation".
    """

    def _build(self, profile_name: str, mode_name: str):
        config = ModeConfigurator().build(profile_name, mode_name)
        orch = build_orchestrator(config, {ProviderType.OLLAMA: _FakeProvider()})
        return config, orch

    def test_designlab1_cowork_caps_at_tier2(self):
        config, orch = self._build("tier2_designlab", "cowork")
        self.assertEqual(config.effective_tier_max, 2)
        self.assertIsInstance(orch, DualLLMOrchestrator)

    def test_tasker_p1_cowork_caps_at_tier1(self):
        config, orch = self._build("tier1_tasker", "cowork")
        self.assertEqual(config.effective_tier_max, 1)
        self.assertIsInstance(orch, SingleLLMOrchestrator)

    def test_tier4_profile_with_cowork_reaches_cloud_orchestrator(self):
        config, orch = self._build("tier4_cloud_hybrid", "cowork")
        self.assertEqual(config.effective_tier_max, 4)
        self.assertIsInstance(orch, CloudOrchestrator)

    def test_tier4_profile_with_chat_still_caps_at_mode_tier(self):
        # Mode ceiling still applies: chat caps at 1 even on a tier-4 profile.
        config, orch = self._build("tier4_cloud_hybrid", "chat")
        self.assertEqual(config.effective_tier_max, 1)
        self.assertIsInstance(orch, SingleLLMOrchestrator)


if __name__ == "__main__":
    unittest.main()
