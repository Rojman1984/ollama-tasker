"""
Unit tests -- WorkerManifest (tasker/workers/base.py)
Phase 1 -- SDD Section 6.1
"""
import unittest
# from tasker.workers.base import (
#     WorkerManifest, Capability, ProviderType, ComputeLocation,
#     ToolProtocol, LatencyClass, TaskerPolicyError
# )


class TestWorkerManifest(unittest.TestCase):

    def test_valid_manifest_with_tool_use(self):
        # Construct a valid manifest -- assert no exception raised
        self.skipTest("Phase 1 not yet implemented")

    def test_manifest_without_tool_use_raises(self):
        # Manifest missing TOOL_USE must raise TaskerPolicyError
        self.skipTest("Phase 1 not yet implemented")

    def test_serialization_round_trip(self):
        # to_dict() / from_dict() round-trip equality
        self.skipTest("Phase 1 not yet implemented")

    def test_local_manifest_has_no_usage_level(self):
        # local_hardware manifests must have ollama_usage_level=None
        self.skipTest("Phase 1 not yet implemented")

    def test_ollama_cloud_manifest_has_usage_level(self):
        # ollama_cloud manifests must have ollama_usage_level set
        self.skipTest("Phase 1 not yet implemented")


if __name__ == "__main__":
    unittest.main()