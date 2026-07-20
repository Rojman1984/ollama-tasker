"""
Unit tests -- WorkerRegistry (tasker/workers/registry.py)
Phase 1 -- SDD Section 5.4
"""
import unittest
from pathlib import Path

from tasker.workers.registry import WorkerRegistry
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    OllamaUsageLevel,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)

_REAL_REGISTRY_YAML = (
    Path(__file__).parent.parent.parent / "config" / "workers" / "worker_registry.yaml"
)


def _manifest(
    worker_id: str,
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
    capabilities: set[Capability] | None = None,
    available: bool = True,
    provider: ProviderType = ProviderType.OLLAMA,
) -> WorkerManifest:
    if capabilities is None:
        capabilities = {Capability.TOOL_USE, Capability.CODE}
    return WorkerManifest(
        id=worker_id,
        provider=provider,
        model_id="lfm2.5:latest",
        compute_location=compute_location,
        capabilities=capabilities,
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=(
            OllamaUsageLevel.MEDIUM
            if compute_location == ComputeLocation.OLLAMA_CLOUD else None
        ),
        latency_class=LatencyClass.MEDIUM,
        available=available,
        requires_gpu=False,
        vram_mb=None,
    )


class TestWorkerRegistry(unittest.TestCase):

    def setUp(self):
        self.registry = WorkerRegistry()

    def test_register_local_worker(self):
        m = _manifest("local-w1")
        self.registry.register(m)
        self.assertIs(self.registry.get("local-w1"), m)

    def test_register_ollama_cloud_worker(self):
        m = _manifest("cloud-w1", compute_location=ComputeLocation.OLLAMA_CLOUD)
        self.registry.register(m)
        self.assertIs(self.registry.get("cloud-w1"), m)

    def test_deregister_removes_worker(self):
        self.registry.register(_manifest("w1"))
        self.registry.deregister("w1")
        self.assertIsNone(self.registry.get("w1"))

    def test_deregister_nonexistent_is_safe(self):
        self.registry.deregister("does-not-exist")  # must not raise

    def test_filter_by_capability(self):
        self.registry.register(_manifest("w1", capabilities={Capability.TOOL_USE, Capability.CODE}))
        self.registry.register(_manifest("w2", capabilities={Capability.TOOL_USE, Capability.REASONING}))
        result = self.registry.filter({Capability.CODE})
        ids = {m.id for m in result}
        self.assertIn("w1", ids)
        self.assertNotIn("w2", ids)

    def test_filter_returns_empty_on_no_match(self):
        self.registry.register(_manifest("w1", capabilities={Capability.TOOL_USE}))
        result = self.registry.filter({Capability.VISION})
        self.assertEqual(result, [])

    def test_filter_multi_capability_requires_all(self):
        self.registry.register(_manifest("w1", capabilities={Capability.TOOL_USE, Capability.CODE}))
        self.registry.register(_manifest("w2", capabilities={Capability.TOOL_USE, Capability.CODE, Capability.REASONING}))
        result = self.registry.filter({Capability.CODE, Capability.REASONING})
        ids = {m.id for m in result}
        self.assertIn("w2", ids)
        self.assertNotIn("w1", ids)

    def test_list_all_returns_all_registered(self):
        self.registry.register(_manifest("w1"))
        self.registry.register(_manifest("w2"))
        ids = {m.id for m in self.registry.list_all()}
        self.assertEqual(ids, {"w1", "w2"})

    def test_get_returns_manifest_by_id(self):
        m = _manifest("w1")
        self.registry.register(m)
        self.assertIs(self.registry.get("w1"), m)

    def test_get_missing_returns_none(self):
        self.assertIsNone(self.registry.get("missing"))

    def test_health_check_available_worker(self):
        self.registry.register(_manifest("w1", available=True))
        self.assertTrue(self.registry.health_check("w1"))

    def test_health_check_unavailable_worker(self):
        self.registry.register(_manifest("w1", available=False))
        self.assertFalse(self.registry.health_check("w1"))

    def test_health_check_missing_worker(self):
        self.assertFalse(self.registry.health_check("missing"))


class TestApplyProviderAvailability(unittest.TestCase):
    """
    A worker whose provider has no wired implementation in the active
    provider_map (e.g. selection picks a Fugu worker but only OllamaProvider
    is wired) must be marked unavailable up front -- never selected, then
    failed mid-dispatch with "No provider for X". Same pattern as
    apply_gpu_availability: marked, logged, never silently dropped.
    """

    def setUp(self):
        self.registry = WorkerRegistry()

    def test_worker_with_unwired_provider_marked_unavailable(self):
        self.registry.register(_manifest("fugu-w1", provider=ProviderType.FUGU))
        provider_map = {ProviderType.OLLAMA: object()}
        self.registry.apply_provider_availability(provider_map)
        self.assertFalse(self.registry.get("fugu-w1").available)

    def test_worker_with_wired_provider_stays_available(self):
        self.registry.register(_manifest("ollama-w1", provider=ProviderType.OLLAMA))
        provider_map = {ProviderType.OLLAMA: object()}
        self.registry.apply_provider_availability(provider_map)
        self.assertTrue(self.registry.get("ollama-w1").available)

    def test_never_dropped_from_list_all(self):
        self.registry.register(_manifest("fugu-w1", provider=ProviderType.FUGU))
        provider_map = {ProviderType.OLLAMA: object()}
        self.registry.apply_provider_availability(provider_map)
        ids = {m.id for m in self.registry.list_all()}
        self.assertIn("fugu-w1", ids)

    def test_mixed_registry_only_unwired_marked_unavailable(self):
        self.registry.register(_manifest("ollama-w1", provider=ProviderType.OLLAMA))
        self.registry.register(_manifest("fugu-w1", provider=ProviderType.FUGU))
        self.registry.register(_manifest("anthropic-w1", provider=ProviderType.ANTHROPIC))
        provider_map = {ProviderType.OLLAMA: object()}
        self.registry.apply_provider_availability(provider_map)
        self.assertTrue(self.registry.get("ollama-w1").available)
        self.assertFalse(self.registry.get("fugu-w1").available)
        self.assertFalse(self.registry.get("anthropic-w1").available)

    def test_already_unavailable_worker_stays_unavailable(self):
        self.registry.register(
            _manifest("ollama-w1", provider=ProviderType.OLLAMA, available=False)
        )
        provider_map = {ProviderType.OLLAMA: object()}
        self.registry.apply_provider_availability(provider_map)
        self.assertFalse(self.registry.get("ollama-w1").available)


class TestRealWorkerRegistryYaml(unittest.TestCase):
    """
    Regression coverage against the REAL config/workers/worker_registry.yaml
    (not a synthetic fixture) -- Ollama Cloud requires a ":cloud" suffix on
    model_id to route to cloud infrastructure rather than being interpreted
    as a local model pull request. Confirmed live: a bare model_id (e.g.
    "nemotron-3-ultra") returns {"error": "model '...' not found"}, while
    the ":cloud"-suffixed form returns a real response. All 5
    compute_location: ollama_cloud entries were missing this suffix and
    were fixed in the same change that added this test -- this guards
    against that specific class of bug silently reappearing.
    """

    @classmethod
    def setUpClass(cls):
        cls.registry = WorkerRegistry.load_from_yaml(_REAL_REGISTRY_YAML)

    def test_registry_file_loads_at_least_one_worker(self):
        # Sanity check that the file actually parsed -- load_from_yaml
        # silently swallows per-entry errors, so an empty result here
        # would otherwise mask every other assertion in this class.
        self.assertGreater(len(self.registry.list_all()), 0)

    def test_every_ollama_cloud_worker_has_cloud_suffix(self):
        cloud_workers = [
            m for m in self.registry.list_all()
            if m.compute_location == ComputeLocation.OLLAMA_CLOUD
        ]
        self.assertGreater(
            len(cloud_workers), 0,
            "expected at least one ollama_cloud worker in the real registry -- "
            "if this fails, the test itself may need updating, not the registry",
        )
        for m in cloud_workers:
            self.assertTrue(
                m.model_id.endswith(":cloud"),
                f"worker {m.id!r} has compute_location=OLLAMA_CLOUD but "
                f"model_id={m.model_id!r} is missing the required ':cloud' suffix",
            )

    def test_local_and_direct_cloud_workers_do_not_require_cloud_suffix(self):
        # The suffix is Ollama-Cloud-specific -- local_hardware/direct_cloud
        # (Anthropic/OpenAI/Fugu) entries must be untouched by this fix.
        non_ollama_cloud = [
            m for m in self.registry.list_all()
            if m.compute_location != ComputeLocation.OLLAMA_CLOUD
        ]
        self.assertGreater(len(non_ollama_cloud), 0)
        for m in non_ollama_cloud:
            self.assertFalse(m.model_id.endswith(":cloud"))


if __name__ == "__main__":
    unittest.main()
