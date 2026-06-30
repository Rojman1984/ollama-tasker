"""
Unit tests -- EpisodicMemoryBridge implementations (tasker/session/episodic.py)
Phase 7 -- SDD Section 5.11
"""
import json
import tempfile
import unittest
from pathlib import Path

from tasker.session.episodic import (
    EpisodicMemoryBridge,
    JsonlEpisodicMemoryBridge,
    NullEpisodicMemoryBridge,
)


# ------------------------------------------------------------------ #
# NullEpisodicMemoryBridge
# ------------------------------------------------------------------ #

class TestNullBridge(unittest.TestCase):

    def setUp(self):
        self.bridge = NullEpisodicMemoryBridge()

    def test_record_event_returns_zero(self):
        pos = self.bridge.record_event("session-1", {"kind": "step_completed", "step_index": 0})
        self.assertEqual(pos, 0)

    def test_read_since_returns_empty(self):
        self.bridge.record_event("session-1", {"kind": "step_completed"})
        result = self.bridge.read_since("session-1", 0)
        self.assertEqual(result, [])

    def test_is_episodic_memory_bridge(self):
        self.assertIsInstance(self.bridge, EpisodicMemoryBridge)


# ------------------------------------------------------------------ #
# JsonlEpisodicMemoryBridge
# ------------------------------------------------------------------ #

class TestJsonlBridge(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.bridge = JsonlEpisodicMemoryBridge(Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_is_episodic_memory_bridge(self):
        self.assertIsInstance(self.bridge, EpisodicMemoryBridge)

    def test_record_first_event_returns_position_zero(self):
        pos = self.bridge.record_event("sess", {"kind": "start"})
        self.assertEqual(pos, 0)

    def test_record_second_event_returns_position_one(self):
        self.bridge.record_event("sess", {"kind": "step_completed", "step_index": 0})
        pos = self.bridge.record_event("sess", {"kind": "step_completed", "step_index": 1})
        self.assertEqual(pos, 1)

    def test_read_since_zero_returns_all_events(self):
        self.bridge.record_event("sess", {"kind": "a"})
        self.bridge.record_event("sess", {"kind": "b"})
        self.bridge.record_event("sess", {"kind": "c"})
        events = self.bridge.read_since("sess", 0)
        self.assertEqual(len(events), 3)

    def test_read_since_one_skips_first(self):
        self.bridge.record_event("sess", {"kind": "first"})
        self.bridge.record_event("sess", {"kind": "second"})
        self.bridge.record_event("sess", {"kind": "third"})
        events = self.bridge.read_since("sess", 1)
        self.assertEqual(len(events), 2)
        self.assertEqual(events[0]["kind"], "second")

    def test_read_since_past_end_returns_empty(self):
        self.bridge.record_event("sess", {"kind": "only"})
        events = self.bridge.read_since("sess", 5)
        self.assertEqual(events, [])

    def test_events_stored_as_jsonl(self):
        self.bridge.record_event("s1", {"kind": "alpha"})
        self.bridge.record_event("s1", {"kind": "beta"})
        path = Path(self._tmp.name) / "s1.jsonl"
        lines = path.read_text(encoding="utf-8").strip().splitlines()
        self.assertEqual(len(lines), 2)
        first = json.loads(lines[0])
        self.assertEqual(first["kind"], "alpha")

    def test_event_is_stamped_with_timestamp(self):
        self.bridge.record_event("sess", {"kind": "step_completed"})
        events = self.bridge.read_since("sess", 0)
        self.assertIn("_ts", events[0])

    def test_session_isolation(self):
        self.bridge.record_event("sess-a", {"kind": "a"})
        self.bridge.record_event("sess-b", {"kind": "b"})
        events_a = self.bridge.read_since("sess-a", 0)
        events_b = self.bridge.read_since("sess-b", 0)
        self.assertEqual(len(events_a), 1)
        self.assertEqual(len(events_b), 1)
        self.assertEqual(events_a[0]["kind"], "a")
        self.assertEqual(events_b[0]["kind"], "b")

    def test_read_from_nonexistent_session_returns_empty(self):
        events = self.bridge.read_since("does-not-exist", 0)
        self.assertEqual(events, [])

    def test_event_payload_preserved(self):
        self.bridge.record_event("sess", {"kind": "step_completed", "step_index": 3, "output": "done"})
        events = self.bridge.read_since("sess", 0)
        self.assertEqual(events[0]["step_index"], 3)
        self.assertEqual(events[0]["output"], "done")


# ------------------------------------------------------------------ #
# CoworkRunner wiring — episodic_log_position in checkpoint
# ------------------------------------------------------------------ #

class TestCoworkRunnerEpisodicWiring(unittest.IsolatedAsyncioTestCase):

    async def test_episodic_log_position_saved_to_checkpoint(self):
        import tempfile
        from pathlib import Path
        from datetime import datetime, timezone

        from tasker.modes.cowork import COWORK_MODE, CoworkRunner
        from tasker.session.budget import OllamaSessionBudget
        from tasker.session.checkpoint import CheckpointStore
        from tasker.session.manager import SessionManager
        from tasker.session.notifier import LogNotifier
        from tasker.workers.base import (
            AgentRole, Capability, ExecutionPlan, OllamaPlan, PlanStep, StepStatus,
        )

        with tempfile.TemporaryDirectory() as tmp:
            store_dir  = Path(tmp) / "checkpoints"
            bridge_dir = Path(tmp) / "episodic"

            budget = OllamaSessionBudget(
                plan=OllamaPlan.PRO,
                window_start=datetime.now(tz=timezone.utc),
            )
            store      = CheckpointStore(store_dir=store_dir)
            notifier   = LogNotifier("tasker.test")
            session_mgr = SessionManager(budget=budget, store=store, notifier=notifier)
            bridge     = JsonlEpisodicMemoryBridge(bridge_dir)

            executed: list[int] = []

            async def _step_fn(step: PlanStep) -> str:
                executed.append(step.index)
                if step.index == 0:
                    budget.record_usage(3000.0)   # exhaust budget → pause after step 0
                return f"output_{step.index}"

            plan = ExecutionPlan(
                plan_id="ep-test",
                original_task="episodic test task",
                steps=[
                    PlanStep(index=0, description="first step", role=AgentRole.WORKER,
                             required_capabilities={Capability.TOOL_USE},
                             depends_on=[], status=StepStatus.PENDING),
                    PlanStep(index=1, description="second step", role=AgentRole.WORKER,
                             required_capabilities={Capability.TOOL_USE},
                             depends_on=[0], status=StepStatus.PENDING),
                ],
                dependency_graph={0: [], 1: [0]},
            )

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                hardware_profile="test",
                episodic_bridge=bridge,
                _step_fn=_step_fn,
            )

            result = await runner.run("episodic test task", plan)

            self.assertIsNone(result)             # paused
            self.assertEqual(executed, [0])       # only step 0 ran

            # Check checkpoint captured the episodic position (step 0 was recorded)
            cp = store.load_latest()
            self.assertIsNotNone(cp)
            self.assertEqual(cp.episodic_log_position, 0)   # position of the event

            # Check the event was actually recorded
            events = bridge.read_since(session_mgr.session_id, 0)
            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["step_index"], 0)
            self.assertEqual(events[0]["kind"], "step_completed")


if __name__ == "__main__":
    unittest.main()
