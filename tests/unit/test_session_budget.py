"""
Unit tests -- OllamaSessionBudget (tasker/session/budget.py)
Phase 2 -- SDD Sections 5.10 and 6.6
"""
import unittest
from datetime import datetime, timedelta

from tasker.session.budget import OllamaSessionBudget
from tasker.workers.base import OllamaPlan


def _budget(
    plan: OllamaPlan = OllamaPlan.FREE,
    usage: float = 0.0,
    weekly: float = 0.0,
    window_start: datetime | None = None,
) -> OllamaSessionBudget:
    return OllamaSessionBudget(
        plan=plan,
        window_start=window_start or datetime.now().astimezone(),
        usage_consumed=usage,
        weekly_usage_consumed=weekly,
    )


class TestOllamaSessionBudget(unittest.TestCase):

    def test_throttle_at_ninety_percent(self):
        # FREE session limit = 1000; 900 / 1000 = 90% → should_throttle
        b = _budget(usage=900.0)
        self.assertTrue(b.should_throttle)
        # 899 is just under — no throttle
        b2 = _budget(usage=899.9)
        self.assertFalse(b2.should_throttle)

    def test_exhausted_at_one_hundred_percent(self):
        b = _budget(usage=1000.0)
        self.assertTrue(b.is_exhausted)
        # 999 is throttling but not exhausted
        b2 = _budget(usage=999.9)
        self.assertFalse(b2.is_exhausted)
        self.assertTrue(b2.should_throttle)

    def test_window_remaining_calculation(self):
        # Window just started — almost 5 hours should remain
        b = _budget()
        remaining = b.window_remaining
        self.assertGreater(remaining.total_seconds(), 4 * 3600)
        self.assertLessEqual(remaining.total_seconds(), 5 * 3600)

    def test_window_remaining_expired_returns_zero(self):
        old_start = datetime.now().astimezone() - timedelta(hours=6)
        b = _budget(window_start=old_start)
        self.assertEqual(b.window_remaining, timedelta(0))

    def test_weekly_usage_tracked_separately(self):
        # Session at 50%, weekly at 85% (4250/5000 for FREE) → should_throttle via weekly
        b = _budget(usage=500.0, weekly=4250.0)
        self.assertFalse(b.usage_pct >= 0.90)          # session not yet at 90%
        self.assertTrue(b.should_throttle)              # weekly at exactly 85%

    def test_weekly_exhausted_triggers_is_exhausted(self):
        # Session fine, weekly at 100%
        b = _budget(usage=0.0, weekly=5000.0)
        self.assertTrue(b.is_exhausted)

    def test_record_usage_accumulates(self):
        b = _budget()
        b.record_usage(300.0)
        b.record_usage(200.0)
        self.assertAlmostEqual(b.usage_consumed, 500.0)
        self.assertAlmostEqual(b.weekly_usage_consumed, 500.0)

    def test_reset_window_clears_session_usage(self):
        b = _budget(usage=800.0, weekly=2000.0)
        b.reset_window()
        self.assertAlmostEqual(b.usage_consumed, 0.0)
        self.assertAlmostEqual(b.weekly_usage_consumed, 2000.0)  # weekly preserved

    def test_snapshot_round_trip(self):
        b = _budget(plan=OllamaPlan.PRO, usage=1500.0, weekly=7500.0)
        snap = b.snapshot()
        d = snap.to_dict()
        snap2 = snap.from_dict(d)
        self.assertAlmostEqual(snap2.usage_pct, snap.usage_pct)
        self.assertEqual(snap2.plan, "pro")


if __name__ == "__main__":
    unittest.main()
