"""
Unit tests -- WorkerRegistry (tasker/workers/registry.py)
Phase 1 -- SDD Section 5.4
"""
import unittest
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


def _manifest(
    worker_id: str,
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
    capabilities: set[Capability] | None = None,
    available: bool = True,
) -> WorkerManifest:
    if capabilities is None:
        capabilities = {Capability.TOOL_USE, Capability.CODE}
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
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


if __name__ == "__main__":
    unittest.main()
