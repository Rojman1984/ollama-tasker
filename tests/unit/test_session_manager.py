"""
Unit tests -- SessionManager state machine (tasker/session/manager.py)
Phase 2 -- SDD Section 9
"""
import unittest


class TestSessionManager(unittest.TestCase):

    def test_running_to_throttling_at_ninety_percent(self):
        self.skipTest("Phase 2 not yet implemented")

    def test_throttling_to_pausing_at_one_hundred_percent(self):
        self.skipTest("Phase 2 not yet implemented")

    def test_current_step_completes_before_pause(self):
        self.skipTest("Phase 2 not yet implemented")

    def test_checkpoint_written_on_pause(self):
        self.skipTest("Phase 2 not yet implemented")

    def test_auto_resume_timer_fires(self):
        self.skipTest("Phase 2 not yet implemented")

    def test_manual_resume_from_checkpoint_id(self):
        self.skipTest("Phase 2 not yet implemented")


if __name__ == "__main__":
    unittest.main()