"""
Unit tests -- SessionManager state machine (tasker/session/manager.py)
Phase 2 -- SDD Section 9
"""
import tempfile
import unittest
from datetime import datetime, timedelta
from pathlib import Path

from tasker.session.budget import BudgetSnapshot, OllamaSessionBudget
from tasker.session.checkpoint import Checkpoint, CheckpointStore
from tasker.session.manager import SessionManager
from tasker.session.notifier import NotifierBase, SessionEvent
from tasker.workers.base import (
    AgentRole,
    Capability,
    ExecutionPlan,
    OllamaPlan,
    PlanStep,
    SessionDirective,
    SessionState,
    StepStatus,
)


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

class _NullNotifier(NotifierBase):
    """Captures events without printing."""

    def __init__(self):
        self.received: list[SessionEvent] = []

    async def send(self, event: SessionEvent) -> None:
        self.received.append(event)


def _budget(usage: float = 0.0, weekly: float = 0.0, plan: OllamaPlan = OllamaPlan.FREE,
            window_start: datetime | None = None) -> OllamaSessionBudget:
    return OllamaSessionBudget(
        plan=plan,
        window_start=window_start or datetime.now().astimezone(),
        usage_consumed=usage,
        weekly_usage_consumed=weekly,
    )


def _snapshot() -> BudgetSnapshot:
    return BudgetSnapshot(
        captured_at=datetime.now().astimezone(),
        usage_pct=1.0,
        weekly_usage_pct=0.5,
        window_remaining_s=0.0,
        plan="free",
    )


def _plan() -> ExecutionPlan:
    steps = [
        PlanStep(
            index=0,
            description="execute task",
            role=AgentRole.WORKER,
            required_capabilities={Capability.TOOL_USE},
            depends_on=[],
            status=StepStatus.PENDING,
        )
    ]
    return ExecutionPlan(
        plan_id="mgr-test-plan",
        original_task="test task",
        steps=steps,
        dependency_graph={0: []},
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


def _manager(budget: OllamaSessionBudget, store: CheckpointStore,
             notifier: _NullNotifier | None = None,
             auto_resume: bool = True) -> SessionManager:
    return SessionManager(
        budget=budget,
        store=store,
        notifier=notifier or _NullNotifier(),
        auto_resume=auto_resume,
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestSessionManager(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = CheckpointStore(store_dir=Path(self._tmp.name))

    def tearDown(self):
        self._tmp.cleanup()

    def test_running_to_throttling_at_ninety_percent(self):
        b = _budget(usage=900.0)
        mgr = _manager(b, self.store)
        self.assertEqual(mgr.state, SessionState.RUNNING)
        directive = mgr.tick()
        self.assertEqual(directive, SessionDirective.CONTINUE_LOCAL_ONLY)
        self.assertEqual(mgr.state, SessionState.THROTTLING)

    def test_throttling_to_pausing_at_one_hundred_percent(self):
        b = _budget(usage=1000.0)
        mgr = _manager(b, self.store)
        directive = mgr.tick()
        self.assertEqual(directive, SessionDirective.PAUSE)
        self.assertEqual(mgr.state, SessionState.PAUSING)

    def test_current_step_completes_before_pause(self):
        b = _budget(usage=1000.0)
        mgr = _manager(b, self.store)
        mgr.tick()
        self.assertEqual(mgr.state, SessionState.PAUSING)  # not yet PAUSED
        self.assertEqual(mgr.tick(), SessionDirective.PAUSE)
        self.assertEqual(mgr.state, SessionState.PAUSING)

    async def test_checkpoint_written_on_pause(self):
        b = _budget(usage=1000.0)
        notifier = _NullNotifier()
        mgr = _manager(b, self.store, notifier=notifier)
        mgr.tick()

        cp = _checkpoint(self.store)
        await mgr.pause(cp)

        self.assertEqual(mgr.state, SessionState.PAUSED)
        loaded = self.store.load(cp.id)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.id, cp.id)
        self.assertEqual(len(notifier.received), 1)
        self.assertEqual(notifier.received[0].kind, "paused")

    def test_auto_resume_flag_when_window_expired(self):
        old_start = datetime.now().astimezone() - timedelta(hours=6)
        b = _budget(usage=1000.0, window_start=old_start)
        mgr = _manager(b, self.store, auto_resume=True)
        mgr._state = SessionState.PAUSED
        self.assertTrue(mgr.should_auto_resume(datetime.now().astimezone()))

    async def test_manual_resume_from_checkpoint_id(self):
        b = _budget(usage=1000.0)
        notifier = _NullNotifier()
        mgr = _manager(b, self.store, notifier=notifier)
        mgr.tick()

        cp = _checkpoint(self.store)
        await mgr.pause(cp)
        self.assertEqual(mgr.state, SessionState.PAUSED)

        resumed_cp = await mgr.resume(cp.id)
        self.assertIsNotNone(resumed_cp)
        self.assertEqual(resumed_cp.id, cp.id)
        self.assertEqual(mgr.state, SessionState.RUNNING)
        self.assertEqual(notifier.received[-1].kind, "resumed")

    async def test_resume_missing_checkpoint_returns_none(self):
        b = _budget(usage=1000.0)
        mgr = _manager(b, self.store)
        mgr._state = SessionState.PAUSED
        result = await mgr.resume("does-not-exist")
        self.assertIsNone(result)
        self.assertEqual(mgr.state, SessionState.PAUSED)

    def test_healthy_budget_returns_continue(self):
        b = _budget(usage=0.0)
        mgr = _manager(b, self.store)
        self.assertEqual(mgr.tick(), SessionDirective.CONTINUE)
        self.assertEqual(mgr.state, SessionState.RUNNING)

    def test_paused_state_returns_hold(self):
        b = _budget(usage=1000.0)
        mgr = _manager(b, self.store)
        mgr._state = SessionState.PAUSED
        self.assertEqual(mgr.tick(), SessionDirective.HOLD)

    async def test_resumed_checkpoint_plan_preserved(self):
        """Resume must restore the ExecutionPlan with correct step statuses."""
        b = _budget(usage=1000.0)
        notifier = _NullNotifier()
        mgr = _manager(b, self.store, notifier=notifier)
        mgr.tick()

        p = _plan()
        p.steps[0].status = StepStatus.ACTIVE
        cp = Checkpoint.new(
            mode="code",
            hardware_profile="tier1_tasker",
            original_task="preserve plan",
            budget_snapshot=_snapshot(),
            plan=p,
            current_step_index=0,
        )
        self.store.save(cp)
        await mgr.pause(cp)

        resumed = await mgr.resume(cp.id)
        self.assertIsNotNone(resumed)
        self.assertEqual(resumed.plan.steps[0].status, StepStatus.ACTIVE)
        self.assertEqual(resumed.original_task, "preserve plan")


if __name__ == "__main__":
    unittest.main()
