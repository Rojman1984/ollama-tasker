"""
Unit tests -- WorkerRegistry (tasker/workers/registry.py)
Phase 1 -- SDD Section 5.4
"""
import unittest
# from tasker.workers.registry import WorkerRegistry


class TestWorkerRegistry(unittest.TestCase):

    def setUp(self):
        # self.registry = WorkerRegistry()
        pass

    def test_register_local_worker(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_register_ollama_cloud_worker(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_deregister_removes_worker(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_filter_by_capability(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_filter_returns_empty_on_no_match(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_list_all_returns_all_registered(self):
        self.skipTest("Phase 1 not yet implemented")

    def test_get_returns_manifest_by_id(self):
        self.skipTest("Phase 1 not yet implemented")


if __name__ == "__main__":
    unittest.main()