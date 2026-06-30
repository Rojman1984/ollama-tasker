"""
Unit tests -- OllamaCloudConcurrencyManager (tasker/session/concurrency.py)
Phase 1 -- SDD Section 5.9
"""
import unittest
from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.workers.base import OllamaPlan


class TestConcurrencyManager(unittest.IsolatedAsyncioTestCase):

    async def test_free_plan_has_one_slot(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        self.assertEqual(mgr.max_slots, 1)

    async def test_pro_plan_has_three_slots(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
        self.assertEqual(mgr.max_slots, 3)

    async def test_max_plan_has_ten_slots(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.MAX)
        self.assertEqual(mgr.max_slots, 10)

    async def test_acquire_within_limit_returns_true(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        acquired = await mgr.try_acquire()
        self.assertTrue(acquired)

    async def test_acquire_beyond_limit_returns_false(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        r1 = await mgr.try_acquire()
        r2 = await mgr.try_acquire()
        self.assertTrue(r1)
        self.assertFalse(r2)  # one slot, already taken

    async def test_release_restores_slot(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        await mgr.try_acquire()
        await mgr.release()
        acquired = await mgr.try_acquire()
        self.assertTrue(acquired)

    async def test_pro_plan_allows_three_concurrent(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
        r1 = await mgr.try_acquire()
        r2 = await mgr.try_acquire()
        r3 = await mgr.try_acquire()
        r4 = await mgr.try_acquire()
        self.assertTrue(r1 and r2 and r3)
        self.assertFalse(r4)

    async def test_slots_available_property(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
        self.assertEqual(mgr.slots_available, 3)
        await mgr.try_acquire()
        self.assertEqual(mgr.slots_available, 2)
        await mgr.try_acquire()
        self.assertEqual(mgr.slots_available, 1)

    async def test_is_full_when_at_limit(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        self.assertFalse(mgr.is_full)
        await mgr.try_acquire()
        self.assertTrue(mgr.is_full)

    async def test_is_full_false_after_release(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        await mgr.try_acquire()
        await mgr.release()
        self.assertFalse(mgr.is_full)

    async def test_slot_context_manager_acquires_and_releases(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        async with mgr.slot() as acquired:
            self.assertTrue(acquired)
            self.assertEqual(mgr.slots_available, 0)
        self.assertEqual(mgr.slots_available, 1)

    async def test_slot_context_manager_yields_false_when_full(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        await mgr.try_acquire()  # fill the one slot
        async with mgr.slot() as acquired:
            self.assertFalse(acquired)
        self.assertEqual(mgr.slots_available, 0)  # still 0; nothing released

    async def test_release_is_idempotent_at_zero(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        await mgr.release()  # should not raise or go negative
        self.assertEqual(mgr.slots_available, 1)


if __name__ == "__main__":
    unittest.main()
