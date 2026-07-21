"""
Unit tests -- CoworkRunner streaming event contract (SDD 7.5a)
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tasker.modes.cowork import (
    COWORK_MODE,
    Done,
    Paused,
    StepCompleted,
    StepStarted,
    SynthesisDelta,
    CoworkRunner,
)
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import CheckpointStore
from tasker.session.manager import SessionManager
from tasker.session.notifier import LogNotifier
from tasker.workers.base import (
    AgentRole,
    Capability,
    ExecutionPlan,
    OllamaPlan,
    PlanStep,
    SessionState,
    StepStatus,
)


def _plan(task: str = "test task", steps: int = 3) -> ExecutionPlan:
    ps = [
        PlanStep(
            index=i,
            description=f"step {i}",
            role=AgentRole.WORKER,
            required_capabilities={Capability.TOOL_USE},
            depends_on=list(range(i)),
        )
        for i in range(steps)
    ]
    return ExecutionPlan(
        plan_id=f"plan-{task[:8]}",
        original_task=task,
        steps=ps,
        dependency_graph={i: list(range(i)) for i in range(steps)},
    )


def _fresh_budget() -> OllamaSessionBudget:
    return OllamaSessionBudget(
        plan=OllamaPlan.PRO,
        window_start=datetime.now().astimezone(),
        usage_consumed=0.0,
    )


def _exhausted_budget() -> OllamaSessionBudget:
    return OllamaSessionBudget(
        plan=OllamaPlan.PRO,
        window_start=datetime.now().astimezone(),
        usage_consumed=3000.0,
    )


class TestCoworkRunnerAstream(unittest.IsolatedAsyncioTestCase):

    async def test_astream_yields_step_and_synthesis_events(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            session_mgr = SessionManager(_fresh_budget(), store, LogNotifier(), auto_resume=False)

            executed: list[int] = []

            async def _step_fn(step: PlanStep) -> str:
                executed.append(step.index)
                return f"output_of_step_{step.index}"

            async def _synthesize_stream_fn(task: str, records: list[dict]):
                yield "Synthesis "
                yield "complete."

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                _step_fn=_step_fn,
                _synthesize_stream_fn=_synthesize_stream_fn,
            )

            plan = _plan("multi-step task", steps=2)
            events = [e async for e in runner.astream("multi-step task", plan)]

            self.assertEqual(executed, [0, 1])
            self.assertEqual(store.list_all(), [])

            # Event sequence assertions
            self.assertIsInstance(events[0], StepStarted)
            self.assertEqual(events[0].step_index, 0)
            self.assertIsInstance(events[1], StepCompleted)
            self.assertEqual(events[1].step_index, 0)
            self.assertEqual(events[1].output, "output_of_step_0")
            self.assertIsInstance(events[2], StepStarted)
            self.assertEqual(events[2].step_index, 1)
            self.assertIsInstance(events[3], StepCompleted)
            self.assertEqual(events[3].output, "output_of_step_1")
            self.assertIsInstance(events[4], SynthesisDelta)
            self.assertEqual(events[4].content, "Synthesis ")
            self.assertIsInstance(events[5], SynthesisDelta)
            self.assertEqual(events[5].content, "complete.")
            self.assertIsInstance(events[6], Done)
            self.assertEqual(events[6].result, "Synthesis complete.")

    async def test_astream_falls_back_to_sentence_chunking_when_no_stream_fn(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            session_mgr = SessionManager(_fresh_budget(), store, LogNotifier(), auto_resume=False)

            async def _synthesize_fn(task: str, records: list[dict]) -> str:
                return "First sentence. Second sentence! Third?"

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                _synthesize_fn=_synthesize_fn,
            )

            plan = _plan("chunked task", steps=1)
            events = [e async for e in runner.astream("chunked task", plan)]

            deltas = [e for e in events if isinstance(e, SynthesisDelta)]
            self.assertEqual(len(deltas), 3)
            self.assertEqual(deltas[0].content, "First sentence.")
            self.assertEqual(deltas[1].content, "Second sentence!")
            self.assertEqual(deltas[2].content, "Third?")

            done = [e for e in events if isinstance(e, Done)][0]
            self.assertEqual(done.result, "First sentence. Second sentence! Third?")

    async def test_astream_pauses_mid_plan_and_yields_paused_event(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            budget = _fresh_budget()
            session_mgr = SessionManager(budget, store, LogNotifier(), auto_resume=False)

            executed: list[int] = []

            async def _step_fn(step: PlanStep) -> str:
                executed.append(step.index)
                if step.index == 0:
                    budget.record_usage(3000.0)  # exhaust budget after step 0
                return f"output_of_step_{step.index}"

            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                hardware_profile="tier1_tasker",
                _step_fn=_step_fn,
            )

            plan = _plan("deep task", steps=3)
            events = [e async for e in runner.astream("deep task", plan)]

            self.assertEqual(executed, [0])
            self.assertEqual(session_mgr.state, SessionState.PAUSED)

            # Should see step 0 lifecycle, then Paused, then nothing else.
            self.assertIsInstance(events[0], StepStarted)
            self.assertEqual(events[0].step_index, 0)
            self.assertIsInstance(events[1], StepCompleted)
            self.assertIsInstance(events[2], Paused)
            self.assertTrue(events[2].checkpoint_id)
            self.assertEqual(len([e for e in events if isinstance(e, Done)]), 0)

            checkpoints = store.list_all()
            self.assertEqual(len(checkpoints), 1)
            self.assertEqual(checkpoints[0].current_step_index, 1)
            self.assertEqual(checkpoints[0].completed_steps[0]["output"], "output_of_step_0")


class TestCoworkRunnerBackwardCompat(unittest.IsolatedAsyncioTestCase):

    async def test_run_without_synthesizer_returns_joined_outputs(self):
        """Existing run()-level tests rely on this behavior."""
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            session_mgr = SessionManager(_fresh_budget(), store, LogNotifier(), auto_resume=False)
            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
            )
            plan = _plan("compat task", steps=2)
            result = await runner.run("compat task", plan)

            self.assertEqual(result, "[step 0: step 0]\n[step 1: step 1]")
            self.assertEqual(store.list_all(), [])
            self.assertTrue(all(s.status == StepStatus.COMPLETED for s in plan.steps))

    async def test_run_returns_none_on_exhausted_budget(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            store = CheckpointStore(Path(tmpdir))
            session_mgr = SessionManager(_exhausted_budget(), store, LogNotifier(), auto_resume=False)
            runner = CoworkRunner(
                mode=COWORK_MODE,
                session_mgr=session_mgr,
                store=store,
                hardware_profile="tier1_tasker",
            )
            plan = _plan("exhausted task", steps=2)
            result = await runner.run("exhausted task", plan)

            self.assertIsNone(result)
            self.assertEqual(session_mgr.state, SessionState.PAUSED)
            self.assertEqual(len(store.list_all()), 1)


if __name__ == "__main__":
    unittest.main()
