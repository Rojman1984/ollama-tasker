"""
Unit tests -- WorkerSelector (tasker/workers/registry.py)
Phase 1 -- SDD Section 5.5
"""
import unittest
# from tasker.workers.registry import WorkerSelector
# from tasker.workers.base import RoutingPolicy, PrivacyTier, TaskerPolicyError


class TestWorkerSelector(unittest.TestCase):

    def test_cost_optimized_prefers_local(self):
        # LOCAL_HARDWARE ranked before OLLAMA_CLOUD before DIRECT_CLOUD
        self.skipTest("Phase 1 not yet implemented")

    def test_capability_first_selects_highest_scored(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_private_hard_block_local_available(self):
        # LOCAL_ONLY + local worker present -> selects local worker
        self.skipTest("Phase 1 not yet implemented")

    def test_private_hard_block_no_local_raises(self):
        # LOCAL_ONLY + no local workers -> raises TaskerPolicyError
        self.skipTest("Phase 1 not yet implemented")

    def test_ollama_cloud_excluded_when_no_slots(self):
        # slots_available == 0 -> OLLAMA_CLOUD candidates removed
        self.skipTest("Phase 1 not yet implemented")

    def test_heavy_models_penalized_when_throttling(self):
        # usage_level 3-4 penalized when should_throttle=True
        self.skipTest("Phase 1 not yet implemented")


if __name__ == "__main__":
    unittest.main()