"""
Unit tests -- WorkerManifest (tasker/workers/base.py)
Phase 1 -- SDD Section 6.1
"""
import unittest
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    OllamaUsageLevel,
    ProviderType,
    TaskerPolicyError,
    ToolProtocol,
    WorkerManifest,
)


def _manifest(
    worker_id: str = "w1",
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
    capabilities: set[Capability] | None = None,
    ollama_usage_level: OllamaUsageLevel | None = None,
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
        ollama_usage_level=ollama_usage_level,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class TestWorkerManifest(unittest.TestCase):

    def test_valid_manifest_with_tool_use(self):
        m = _manifest()
        self.assertEqual(m.id, "w1")
        self.assertIn(Capability.TOOL_USE, m.capabilities)

    def test_manifest_without_tool_use_raises(self):
        with self.assertRaises(TaskerPolicyError):
            _manifest(capabilities={Capability.CODE})

    def test_serialization_round_trip(self):
        m = _manifest(
            worker_id="rt-test",
            ollama_usage_level=OllamaUsageLevel.MEDIUM,
            compute_location=ComputeLocation.OLLAMA_CLOUD,
        )
        m2 = WorkerManifest.from_dict(m.to_dict())
        self.assertEqual(m.id, m2.id)
        self.assertEqual(m.capabilities, m2.capabilities)
        self.assertEqual(m.compute_location, m2.compute_location)
        self.assertEqual(m.ollama_usage_level, m2.ollama_usage_level)
        self.assertEqual(m.provider, m2.provider)

    def test_local_manifest_has_no_usage_level(self):
        m = _manifest(compute_location=ComputeLocation.LOCAL_HARDWARE)
        self.assertIsNone(m.ollama_usage_level)

    def test_ollama_cloud_manifest_has_usage_level(self):
        m = _manifest(
            compute_location=ComputeLocation.OLLAMA_CLOUD,
            ollama_usage_level=OllamaUsageLevel.MEDIUM,
        )
        self.assertEqual(m.ollama_usage_level, OllamaUsageLevel.MEDIUM)

    def test_capability_scores_default_empty(self):
        m = _manifest()
        self.assertEqual(m.capability_scores, {})

    def test_capability_scores_round_trip(self):
        m = _manifest()
        m.capability_scores = {"HumanEval": 0.85, "MMLU": 0.72}
        d = m.to_dict()
        m2 = WorkerManifest.from_dict(d)
        self.assertAlmostEqual(m2.capability_scores["HumanEval"], 0.85)


if __name__ == "__main__":
    unittest.main()
