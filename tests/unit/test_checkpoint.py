"""
Unit tests -- Checkpoint / CheckpointStore (tasker/session/checkpoint.py)
Phase 2 -- SDD Sections 5.11 and 6.5
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tasker.session.budget import BudgetSnapshot
from tasker.session.checkpoint import Checkpoint, CheckpointStore
from tasker.workers.base import (
    AgentRole,
    Capability,
    ExecutionPlan,
    PlanStep,
    StepStatus,
)


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _snapshot() -> BudgetSnapshot:
    return BudgetSnapshot(
        captured_at=datetime.now().astimezone(),
        usage_pct=0.5,
        weekly_usage_pct=0.3,
        window_remaining_s=9000.0,
        plan="free",
    )


def _plan(task: str = "test task") -> ExecutionPlan:
    steps = [
        PlanStep(
            index=0,
            description="analyze",
            role=AgentRole.THINKER,
            required_capabilities={Capability.TOOL_USE, Capability.REASONING},
            depends_on=[],
            status=StepStatus.PENDING,
        ),
        PlanStep(
            index=1,
            description="execute",
            role=AgentRole.WORKER,
            required_capabilities={Capability.TOOL_USE},
            depends_on=[0],
            status=StepStatus.PENDING,
        ),
    ]
    return ExecutionPlan(
        plan_id="test-plan-001",
        original_task=task,
        steps=steps,
        dependency_graph={0: [], 1: [0]},
    )


def _checkpoint(store: CheckpointStore, **kwargs) -> Checkpoint:
    defaults = dict(
        mode="code",
        hardware_profile="tier1_tasker",
        original_task="test task",
        budget_snapshot=_snapshot(),
        plan=_plan(),
    )
    defaults.update(kwargs)
    cp = Checkpoint.new(**defaults)
    store.save(cp)
    return cp


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestCheckpointStore(unittest.TestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = CheckpointStore(store_dir=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_save_and_load_round_trip(self):
        cp = _checkpoint(self.store)
        loaded = self.store.load(cp.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, cp.id)
        self.assertEqual(loaded.mode, cp.mode)
        self.assertEqual(loaded.original_task, cp.original_task)

    def test_plan_round_trips_correctly(self):
        cp = _checkpoint(self.store)
        loaded = self.store.load(cp.id)
        self.assertEqual(loaded.plan.plan_id, "test-plan-001")
        self.assertEqual(len(loaded.plan.steps), 2)
        self.assertEqual(loaded.plan.steps[0].role, AgentRole.THINKER)
        self.assertEqual(loaded.plan.steps[1].role, AgentRole.WORKER)
        self.assertIn(Capability.REASONING, loaded.plan.steps[0].required_capabilities)

    def test_plan_step_status_preserved(self):
        p = _plan()
        p.steps[0].status = StepStatus.COMPLETED
        cp = Checkpoint.new(
            mode="code",
            hardware_profile="tier1_tasker",
            original_task="task",
            budget_snapshot=_snapshot(),
            plan=p,
        )
        self.store.save(cp)
        loaded = self.store.load(cp.id)
        self.assertEqual(loaded.plan.steps[0].status, StepStatus.COMPLETED)
        self.assertEqual(loaded.plan.steps[1].status, StepStatus.PENDING)

    def test_load_returns_none_for_missing_id(self):
        result = self.store.load("does-not-exist")
        self.assertIsNone(result)

    def test_load_latest_returns_most_recently_saved(self):
        cp1 = _checkpoint(self.store, original_task="task one")
        cp2 = _checkpoint(self.store, original_task="task two")
        latest = self.store.load_latest()
        self.assertIsNotNone(latest)
        self.assertEqual(latest.original_task, "task two")

    def test_load_latest_returns_none_when_empty(self):
        result = self.store.load_latest()
        self.assertIsNone(result)

    def test_list_all_returns_all_saved(self):
        cp1 = _checkpoint(self.store, original_task="task alpha")
        cp2 = _checkpoint(self.store, original_task="task beta")
        all_cps = self.store.list_all()
        ids = {c.id for c in all_cps}
        self.assertIn(cp1.id, ids)
        self.assertIn(cp2.id, ids)
        self.assertEqual(len(all_cps), 2)

    def test_delete_removes_checkpoint(self):
        cp = _checkpoint(self.store)
        deleted = self.store.delete(cp.id)
        self.assertTrue(deleted)
        self.assertIsNone(self.store.load(cp.id))

    def test_delete_missing_returns_false(self):
        result = self.store.delete("ghost-id")
        self.assertFalse(result)

    def test_serialization_preserves_resume_at(self):
        resume_at = datetime.now().astimezone() + timedelta(hours=5)
        cp = _checkpoint(self.store, resume_at=resume_at, auto_resume=True)
        loaded = self.store.load(cp.id)
        self.assertIsNotNone(loaded.resume_at)
        self.assertAlmostEqual(
            loaded.resume_at.timestamp(),
            resume_at.timestamp(),
            delta=1,
        )
        self.assertTrue(loaded.auto_resume)

    def test_serialization_with_none_resume_at(self):
        cp = _checkpoint(self.store, resume_at=None, auto_resume=False)
        loaded = self.store.load(cp.id)
        self.assertIsNone(loaded.resume_at)
        self.assertFalse(loaded.auto_resume)

    def test_step_state_preserved(self):
        cp = _checkpoint(
            self.store,
            completed_steps=[{"step": 0, "result": "done"}],
            current_step_index=1,
            session_context={"key": "value"},
        )
        loaded = self.store.load(cp.id)
        self.assertEqual(loaded.current_step_index, 1)
        self.assertEqual(loaded.completed_steps[0]["result"], "done")
        self.assertEqual(loaded.session_context["key"], "value")


if __name__ == "__main__":
    unittest.main()
