"""
Unit tests -- WorkerSelector (tasker/workers/registry.py)
Phase 1 -- SDD Section 5.5
"""
import unittest
from tasker.workers.registry import WorkerSelector
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    OllamaUsageLevel,
    ProviderType,
    RoutingPolicy,
    PrivacyTier,
    TaskerPolicyError,
    ToolProtocol,
    WorkerManifest,
)


def _manifest(
    worker_id: str,
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
    capabilities: set[Capability] | None = None,
    latency_class: LatencyClass = LatencyClass.MEDIUM,
    ollama_usage_level: OllamaUsageLevel | None = None,
    capability_scores: dict[str, float] | None = None,
    available: bool = True,
) -> WorkerManifest:
    if capabilities is None:
        capabilities = {Capability.TOOL_USE, Capability.CODE}
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="test:latest",
        compute_location=compute_location,
        capabilities=capabilities,
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=ollama_usage_level,
        latency_class=latency_class,
        available=available,
        requires_gpu=False,
        vram_mb=None,
        capability_scores=capability_scores or {},
    )


def _select(
    workers: list[WorkerManifest],
    policy: RoutingPolicy = RoutingPolicy.COST_OPTIMIZED,
    privacy_tier: PrivacyTier = PrivacyTier.ANY_CLOUD,
    slots_available: int = 3,
    should_throttle: bool = False,
    required_capabilities: set[Capability] | None = None,
) -> WorkerManifest:
    if required_capabilities is None:
        required_capabilities = {Capability.TOOL_USE}
    return WorkerSelector.select(
        workers=workers,
        required_capabilities=required_capabilities,
        policy=policy,
        privacy_tier=privacy_tier,
        slots_available=slots_available,
        should_throttle=should_throttle,
    )


class TestWorkerSelector(unittest.TestCase):

    # ------------------------------------------------------------------ #
    # COST_OPTIMIZED
    # ------------------------------------------------------------------ #

    def test_cost_optimized_prefers_local(self):
        local  = _manifest("local",  ComputeLocation.LOCAL_HARDWARE)
        cloud  = _manifest("cloud",  ComputeLocation.OLLAMA_CLOUD,  ollama_usage_level=OllamaUsageLevel.LIGHT)
        direct = _manifest("direct", ComputeLocation.DIRECT_CLOUD)
        result = _select([cloud, direct, local], policy=RoutingPolicy.COST_OPTIMIZED)
        self.assertEqual(result.id, "local")

    def test_cost_optimized_cloud_before_direct_when_no_local(self):
        cloud  = _manifest("cloud",  ComputeLocation.OLLAMA_CLOUD,  ollama_usage_level=OllamaUsageLevel.LIGHT)
        direct = _manifest("direct", ComputeLocation.DIRECT_CLOUD)
        result = _select([direct, cloud], policy=RoutingPolicy.COST_OPTIMIZED)
        self.assertEqual(result.id, "cloud")

    # ------------------------------------------------------------------ #
    # CAPABILITY_FIRST
    # ------------------------------------------------------------------ #

    def test_capability_first_selects_highest_scored(self):
        low  = _manifest("low",  capability_scores={"bench": 0.5})
        high = _manifest("high", capability_scores={"bench": 0.9})
        result = _select([low, high], policy=RoutingPolicy.CAPABILITY_FIRST)
        self.assertEqual(result.id, "high")

    def test_capability_first_no_scores_returns_any(self):
        w1 = _manifest("w1")
        w2 = _manifest("w2")
        result = _select([w1, w2], policy=RoutingPolicy.CAPABILITY_FIRST)
        self.assertIn(result.id, {"w1", "w2"})

    # ------------------------------------------------------------------ #
    # SPEED_OPTIMIZED
    # ------------------------------------------------------------------ #

    def test_speed_optimized_prefers_fast_latency(self):
        slow   = _manifest("slow",   latency_class=LatencyClass.SLOW)
        medium = _manifest("medium", latency_class=LatencyClass.MEDIUM)
        fast   = _manifest("fast",   latency_class=LatencyClass.FAST)
        result = _select([slow, medium, fast], policy=RoutingPolicy.SPEED_OPTIMIZED)
        self.assertEqual(result.id, "fast")

    # ------------------------------------------------------------------ #
    # PRIVATE policy
    # ------------------------------------------------------------------ #

    def test_private_hard_block_local_available(self):
        local = _manifest("local", ComputeLocation.LOCAL_HARDWARE)
        cloud = _manifest("cloud", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.LIGHT)
        result = _select([local, cloud], policy=RoutingPolicy.PRIVATE, privacy_tier=PrivacyTier.LOCAL_ONLY)
        self.assertEqual(result.id, "local")

    def test_private_hard_block_no_local_raises(self):
        cloud = _manifest("cloud", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.LIGHT)
        with self.assertRaises(TaskerPolicyError):
            _select([cloud], policy=RoutingPolicy.COST_OPTIMIZED, privacy_tier=PrivacyTier.LOCAL_ONLY)

    # ------------------------------------------------------------------ #
    # Privacy tier — OLLAMA_CLOUD_OK
    # ------------------------------------------------------------------ #

    def test_ollama_cloud_ok_blocks_direct_cloud(self):
        cloud  = _manifest("cloud",  ComputeLocation.OLLAMA_CLOUD,  ollama_usage_level=OllamaUsageLevel.LIGHT)
        direct = _manifest("direct", ComputeLocation.DIRECT_CLOUD)
        result = _select(
            [cloud, direct],
            policy=RoutingPolicy.COST_OPTIMIZED,
            privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
        )
        self.assertEqual(result.id, "cloud")

    # ------------------------------------------------------------------ #
    # Concurrency
    # ------------------------------------------------------------------ #

    def test_ollama_cloud_excluded_when_no_slots(self):
        local = _manifest("local", ComputeLocation.LOCAL_HARDWARE)
        cloud = _manifest("cloud", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.LIGHT)
        result = _select([local, cloud], slots_available=0)
        self.assertEqual(result.id, "local")

    def test_no_slots_no_local_raises(self):
        cloud = _manifest("cloud", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.LIGHT)
        with self.assertRaises(TaskerPolicyError):
            _select([cloud], slots_available=0)

    # ------------------------------------------------------------------ #
    # Budget throttle
    # ------------------------------------------------------------------ #

    def test_heavy_models_penalized_when_throttling(self):
        heavy = _manifest("heavy", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.HEAVY)
        light = _manifest("light", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.LIGHT)
        result = _select(
            [heavy, light],
            policy=RoutingPolicy.COST_OPTIMIZED,
            privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
            should_throttle=True,
        )
        self.assertEqual(result.id, "light")

    def test_heavy_models_allowed_when_only_option_while_throttling(self):
        heavy = _manifest("heavy", ComputeLocation.OLLAMA_CLOUD, ollama_usage_level=OllamaUsageLevel.HEAVY)
        result = _select(
            [heavy],
            policy=RoutingPolicy.COST_OPTIMIZED,
            privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
            should_throttle=True,
        )
        self.assertEqual(result.id, "heavy")

    # ------------------------------------------------------------------ #
    # Capability filter
    # ------------------------------------------------------------------ #

    def test_workers_missing_capability_excluded(self):
        vision = _manifest("vision", capabilities={Capability.TOOL_USE, Capability.VISION})
        code   = _manifest("code",   capabilities={Capability.TOOL_USE, Capability.CODE})
        result = _select([code, vision], required_capabilities={Capability.TOOL_USE, Capability.VISION})
        self.assertEqual(result.id, "vision")

    def test_no_capable_workers_raises(self):
        w = _manifest("w1", capabilities={Capability.TOOL_USE})
        with self.assertRaises(TaskerPolicyError):
            _select([w], required_capabilities={Capability.TOOL_USE, Capability.VISION})

    # ------------------------------------------------------------------ #
    # Availability filter
    # ------------------------------------------------------------------ #

    def test_unavailable_workers_excluded(self):
        up   = _manifest("up",   available=True)
        down = _manifest("down", available=False)
        result = _select([up, down])
        self.assertEqual(result.id, "up")

    def test_all_unavailable_raises(self):
        down = _manifest("down", available=False)
        with self.assertRaises(TaskerPolicyError):
            _select([down])


if __name__ == "__main__":
    unittest.main()
