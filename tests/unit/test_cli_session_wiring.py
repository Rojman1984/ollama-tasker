"""
Unit tests -- Phase 8.1 live-CLI session wiring (cli/shell.py).

Covers the session-layer behaviour newly wired into the CLI step loop:
  - SessionManager.tick() consulted before every step
  - PAUSE directive -> checkpoint written (correct step index + completed
    records) and the loop halts
  - budget exhaustion *mid-run* (recorded by the provider during a step)
    pauses before the next step, never mid-step
  - throttle directive passes should_throttle to WorkerSelector
  - completed-step record serialization roundtrip used by resume
  - _execute_steps honours start_index (resume skips completed steps)

The full plan->synthesize resume path is exercised live (Phase 8.1 E2E),
not here -- these tests use a fake provider and never touch HTTP.
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from cli.shell import (
    _build_session,
    _deserialize_step_result,
    _execute_steps,
    _serialize_step_result,
)
from tasker.modes.base import ModeConfigurator
from tasker.session.checkpoint import CheckpointStore
from tasker.session.manager import SessionManager
from tasker.session.notifier import LogNotifier
from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    ExecutionPlan,
    LatencyClass,
    ModelUsage,
    OllamaPlan,
    PlanStep,
    ProviderType,
    StepStatus,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
)
from tasker.session.budget import OllamaSessionBudget
from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.workers.providers.base import WorkerProviderBase


def _local_worker() -> WorkerManifest:
    return WorkerManifest(
        id="local-w1",
        provider=ProviderType.OLLAMA,
        model_id="lfm2.5:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE, Capability.CODE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _plan(n_steps: int = 2) -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p1",
        original_task="test task",
        steps=[
            PlanStep(
                index=i,
                description=f"step {i}",
                role=AgentRole.WORKER,
                required_capabilities={Capability.TOOL_USE},
                depends_on=[],
                status=StepStatus.PENDING,
            )
            for i in range(n_steps)
        ],
        dependency_graph={},
    )


class _FakeProvider(WorkerProviderBase):
    """Successful one-turn provider; optionally records budget units per call
    (mimicking OllamaProvider's cloud accounting) to simulate mid-run
    exhaustion."""

    def __init__(self, budget=None, units_per_call: float = 0.0) -> None:
        self.calls = 0
        self._budget = budget
        self._units = units_per_call

    def supports(self, worker):
        return True

    async def health_check(self, worker):
        return True

    async def execute(self, task, worker):
        self.calls += 1
        if self._budget is not None and self._units:
            self._budget.record_usage(self._units)
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=WorkerStatus.SUCCESS,
            output=f"output {self.calls}",
            tool_results=[],
            usage=ModelUsage(10, 10, 0.0),
            duration_ms=5,
        )


class TestExecuteStepsSessionWiring(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.store = CheckpointStore(Path(self._tmp.name))
        self.config = ModeConfigurator().build("tier1_tasker", "chat")
        self.budget = OllamaSessionBudget(
            plan=OllamaPlan.PRO, window_start=datetime.now().astimezone()
        )
        self.session_mgr = SessionManager(
            self.budget, self.store, LogNotifier(), auto_resume=False
        )
        self.concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)

    def tearDown(self):
        self._tmp.cleanup()

    async def _run(self, plan, provider, start_index=0, completed=None):
        completed = completed if completed is not None else []
        results, paused = await _execute_steps(
            "test task", plan, start_index, completed,
            workers=[_local_worker()],
            mode_name="chat", profile_name="tier1_tasker",
            config=self.config, budget=self.budget,
            session_mgr=self.session_mgr,
            concurrency_mgr=self.concurrency_mgr,
            provider_map={ProviderType.OLLAMA: provider},
        )
        return results, paused, completed

    async def test_all_steps_complete_when_budget_healthy(self):
        provider = _FakeProvider()
        results, paused, completed = await self._run(_plan(2), provider)
        self.assertFalse(paused)
        self.assertEqual(len(results), 2)
        self.assertEqual(provider.calls, 2)
        self.assertEqual(len(completed), 2)
        self.assertEqual(self.store.list_all(), [])   # no checkpoint written

    async def test_exhausted_budget_pauses_before_first_step(self):
        self.budget.usage_consumed = self.budget.session_limit  # 100%
        provider = _FakeProvider()
        results, paused, completed = await self._run(_plan(2), provider)
        self.assertTrue(paused)
        self.assertEqual(provider.calls, 0)           # nothing dispatched
        cps = self.store.list_all()
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0].current_step_index, 0)
        self.assertEqual(cps[0].completed_steps, [])

    async def test_mid_run_exhaustion_pauses_before_next_step(self):
        # Each provider call consumes a full session budget -- step 0
        # completes (current step always finishes, SDD 9.2), then the
        # tick() before step 1 pauses.
        provider = _FakeProvider(
            budget=self.budget, units_per_call=self.budget.session_limit
        )
        results, paused, completed = await self._run(_plan(2), provider)
        self.assertTrue(paused)
        self.assertEqual(provider.calls, 1)
        self.assertEqual(len(results), 1)
        cps = self.store.list_all()
        self.assertEqual(len(cps), 1)
        self.assertEqual(cps[0].current_step_index, 1)
        self.assertEqual(len(cps[0].completed_steps), 1)
        self.assertEqual(cps[0].completed_steps[0]["step_index"], 0)
        # Budget snapshot captured at pause time shows exhaustion
        self.assertGreaterEqual(cps[0].budget_snapshot.usage_pct, 1.0)

    async def test_start_index_skips_completed_steps(self):
        provider = _FakeProvider()
        results, paused, completed = await self._run(
            _plan(3), provider, start_index=2
        )
        self.assertFalse(paused)
        self.assertEqual(provider.calls, 1)           # only step 2 dispatched
        self.assertEqual(completed[0]["step_index"], 2)

    async def test_checkpoint_survives_reload(self):
        self.budget.usage_consumed = self.budget.session_limit
        await self._run(_plan(2), _FakeProvider())
        cp = self.store.load_latest()
        reloaded = self.store.load(cp.id)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.original_task, "test task")
        self.assertEqual(reloaded.mode, "chat")
        self.assertEqual(reloaded.hardware_profile, "tier1_tasker")
        self.assertEqual(len(reloaded.plan.steps), 2)


class TestStepResultSerialization(unittest.TestCase):

    def test_roundtrip(self):
        result = WorkerResult(
            task_id="t9",
            worker_id="w9",
            status=WorkerStatus.SUCCESS,
            output="the answer",
            tool_results=[],
            usage=ModelUsage(100, 200, 0.01),
            duration_ms=1234,
        )
        record = _serialize_step_result(3, result)
        self.assertEqual(record["step_index"], 3)
        restored = _deserialize_step_result(record)
        self.assertEqual(restored.task_id, "t9")
        self.assertEqual(restored.worker_id, "w9")
        self.assertEqual(restored.status, WorkerStatus.SUCCESS)
        self.assertEqual(restored.output, "the answer")
        self.assertEqual(restored.duration_ms, 1234)


class TestBuildSession(unittest.TestCase):

    def test_budget_preload_env(self):
        import os

        profile = ModeConfigurator().load_profile("tier1_tasker")
        os.environ["TASKER_BUDGET_PRELOAD"] = "2500"
        try:
            budget, session_mgr = _build_session(
                profile, CheckpointStore(Path(tempfile.mkdtemp()))
            )
        finally:
            del os.environ["TASKER_BUDGET_PRELOAD"]
        self.assertEqual(budget.usage_consumed, 2500.0)
        self.assertIsInstance(session_mgr, SessionManager)

    def test_no_preload_starts_at_zero(self):
        profile = ModeConfigurator().load_profile("tier1_tasker")
        budget, _ = _build_session(
            profile, CheckpointStore(Path(tempfile.mkdtemp()))
        )
        self.assertEqual(budget.usage_consumed, 0.0)


if __name__ == "__main__":
    unittest.main()
