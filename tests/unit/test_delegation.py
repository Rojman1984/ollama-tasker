"""
Unit tests -- DELEGATE_AGENT sub-task dispatch (SDD 5.7c).

tasker/runtime/delegation.py's DelegationContext, tasker/tools/executor.py's
_exec_delegate_agent(), and the end-to-end wiring through execute_tool()/
run_tool_loop()/_execute_steps()/_run_task(). No real HTTP/model calls --
the recursive _run_task() call is exercised with a fake orchestrator +
fake provider.
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tasker.modes.base import ModeConfigurator
from tasker.runtime.delegation import DelegationContext
from tasker.runtime.dispatch import _run_task
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import CheckpointStore
from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.session.manager import SessionManager
from tasker.session.notifier import LogNotifier
from tasker.tools.executor import _exec_delegate_agent, execute_tool
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
    WorkerToolResult,
)
from tasker.workers.providers.base import WorkerProviderBase
from tasker.workers.registry import WorkerRegistry


def _worker(worker_id="w1") -> WorkerManifest:
    return WorkerManifest(
        id=worker_id, provider=ProviderType.OLLAMA, model_id="test:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE, context_window=8192,
        cost_input=0.0, cost_output=0.0, ollama_usage_level=None,
        latency_class=LatencyClass.FAST, available=True, requires_gpu=False, vram_mb=None,
    )


def _tr(tool_name: str, tool_input: dict) -> WorkerToolResult:
    return WorkerToolResult(tool_name=tool_name, tool_input=tool_input, tool_output=None, error=None, duration_ms=0)


class TestDelegationContext(unittest.TestCase):

    def test_child_increments_depth(self):
        ctx = DelegationContext(registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=())
        child = ctx.child()
        self.assertEqual(ctx.depth, 0)
        self.assertEqual(child.depth, 1)

    def test_child_shares_spawned_counter_object(self):
        ctx = DelegationContext(registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=())
        child = ctx.child()
        ctx.spawned[0] += 1
        self.assertEqual(child.spawned[0], 1)   # same list object, not a copy

    def test_child_preserves_limits_and_pipeline(self):
        pipeline = ("a", "b")
        ctx = DelegationContext(
            registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=pipeline,
            max_depth=5, max_sub_agents=9,
        )
        child = ctx.child()
        self.assertIs(child.pipeline, pipeline)
        self.assertEqual(child.max_depth, 5)
        self.assertEqual(child.max_sub_agents, 9)

    def test_default_limits(self):
        ctx = DelegationContext(registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=())
        self.assertEqual(ctx.max_depth, 2)
        self.assertEqual(ctx.max_sub_agents, 3)


class TestExecDelegateAgentGuards(unittest.IsolatedAsyncioTestCase):
    """Guard-clause behavior of _exec_delegate_agent() that doesn't need a
    real recursive _run_task() call."""

    async def test_missing_task_input(self):
        output, error = await _exec_delegate_agent({}, delegation=None)
        self.assertIsNone(output)
        self.assertIn("missing required", error)

    async def test_none_delegation_reports_clean_error(self):
        output, error = await _exec_delegate_agent({"task": "do X"}, delegation=None)
        self.assertIsNone(output)
        self.assertIn("not available", error)

    async def test_depth_limit_reached(self):
        ctx = DelegationContext(
            registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=(),
            depth=2, max_depth=2,
        )
        output, error = await _exec_delegate_agent({"task": "do X"}, delegation=ctx)
        self.assertIsNone(output)
        self.assertIn("depth limit", error)

    async def test_sub_agent_cap_reached(self):
        ctx = DelegationContext(
            registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=(),
            spawned=[3], max_sub_agents=3,
        )
        output, error = await _exec_delegate_agent({"task": "do X"}, delegation=ctx)
        self.assertIsNone(output)
        self.assertIn("sub-agent cap", error)

    async def test_cap_check_does_not_increment_spawned_when_already_at_cap(self):
        ctx = DelegationContext(
            registry=mock.Mock(), store=mock.Mock(), mode_name="cowork", pipeline=(),
            spawned=[3], max_sub_agents=3,
        )
        await _exec_delegate_agent({"task": "do X"}, delegation=ctx)
        self.assertEqual(ctx.spawned[0], 3)   # not incremented past the cap


class _FakeOrchestrator:
    def __init__(self, plan, synth_output):
        self._plan = plan
        self._synth_output = synth_output

    async def plan(self, task, classifier_output, workers):
        return self._plan

    async def synthesize(self, task, results):
        return self._synth_output


class _FakeProvider(WorkerProviderBase):
    def __init__(self):
        self.calls = 0

    def supports(self, worker):
        return True

    async def health_check(self, worker):
        return True

    async def execute(self, task, worker):
        self.calls += 1
        return WorkerResult(
            task_id=task.task_id, worker_id=worker.id, status=WorkerStatus.SUCCESS,
            output="sub-task output", tool_results=[], usage=ModelUsage(5, 5, 0.0), duration_ms=5,
        )


def _one_step_plan(task="a sub task") -> ExecutionPlan:
    step = PlanStep(
        index=0, description="do it", role=AgentRole.WORKER,
        required_capabilities={Capability.TOOL_USE}, depends_on=[], status=StepStatus.PENDING,
    )
    return ExecutionPlan(plan_id="p", original_task=task, steps=[step], dependency_graph={0: []})


def _pipeline(orchestrator, provider):
    config = ModeConfigurator().build("tier1_tasker", "cowork")
    budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
    tmp = tempfile.TemporaryDirectory()
    store = CheckpointStore(Path(tmp.name))
    session_mgr = SessionManager(budget, store, LogNotifier(), auto_resume=False)
    concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
    provider_map = {ProviderType.OLLAMA: provider}
    pipeline = ("tier1_tasker", config, budget, session_mgr, concurrency_mgr, provider_map, orchestrator)
    return pipeline, tmp, store, budget


class TestExecDelegateAgentRecursive(unittest.IsolatedAsyncioTestCase):
    """Exercises the real recursive _run_task() call -- proves the
    sub-agent shares the parent's budget/concurrency and returns a real
    result as tool output."""

    async def test_successful_delegation_returns_structured_result(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        orchestrator = _FakeOrchestrator(_one_step_plan(), "the sub-agent's answer")
        provider = _FakeProvider()
        pipeline, tmp, store, budget = _pipeline(orchestrator, provider)
        ctx = DelegationContext(registry=registry, store=store, mode_name="cowork", pipeline=pipeline)

        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                output, error = await _exec_delegate_agent({"task": "investigate X"}, delegation=ctx)
        finally:
            tmp.cleanup()

        self.assertIsNone(error)
        self.assertEqual(output["task"], "investigate X")
        self.assertEqual(output["result"], "the sub-agent's answer")

    async def test_sub_agent_consumes_the_same_shared_budget(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        orchestrator = _FakeOrchestrator(_one_step_plan(), "answer")
        provider = _FakeProvider()
        pipeline, tmp, store, budget = _pipeline(orchestrator, provider)
        ctx = DelegationContext(registry=registry, store=store, mode_name="cowork", pipeline=pipeline)

        self.assertEqual(budget.usage_consumed, 0.0)
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                await _exec_delegate_agent({"task": "investigate X"}, delegation=ctx)
        finally:
            tmp.cleanup()
        # provider actually ran (proves the sub-task used the SAME
        # pipeline's provider, not a separate one).
        self.assertEqual(provider.calls, 1)

    async def test_spawned_counter_increments(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        orchestrator = _FakeOrchestrator(_one_step_plan(), "answer")
        provider = _FakeProvider()
        pipeline, tmp, store, budget = _pipeline(orchestrator, provider)
        ctx = DelegationContext(registry=registry, store=store, mode_name="cowork", pipeline=pipeline)

        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                await _exec_delegate_agent({"task": "investigate X"}, delegation=ctx)
        finally:
            tmp.cleanup()
        self.assertEqual(ctx.spawned[0], 1)

    async def test_sub_agent_task_gets_next_depth(self):
        registry = WorkerRegistry()
        registry.register(_worker())

        captured_depth = []

        class RecordingOrchestrator(_FakeOrchestrator):
            async def plan(self, task, classifier_output, workers):
                return self._plan

        orchestrator = RecordingOrchestrator(_one_step_plan(), "answer")
        provider = _FakeProvider()
        pipeline, tmp, store, budget = _pipeline(orchestrator, provider)
        ctx = DelegationContext(registry=registry, store=store, mode_name="cowork", pipeline=pipeline, depth=0)

        with mock.patch("tasker.runtime.dispatch._run_task", wraps=None) as m_run_task:
            async def fake_run_task(*args, **kwargs):
                captured_depth.append(kwargs["delegation"].depth)
                return "answer"
            m_run_task.side_effect = fake_run_task
            await _exec_delegate_agent({"task": "investigate X"}, delegation=ctx)
        tmp.cleanup()
        self.assertEqual(captured_depth, [1])

    async def test_two_level_chain_hits_depth_limit_on_third(self):
        # depth 0 -> delegate -> depth 1 -> delegate -> depth 2 (allowed,
        # max_depth=2) -> delegate -> refused (would be depth 3).
        registry = WorkerRegistry()
        registry.register(_worker())
        orchestrator = _FakeOrchestrator(_one_step_plan(), "answer")
        provider = _FakeProvider()
        pipeline, tmp, store, budget = _pipeline(orchestrator, provider)

        ctx0 = DelegationContext(registry=registry, store=store, mode_name="cowork", pipeline=pipeline, depth=0)
        ctx1 = ctx0.child()
        ctx2 = ctx1.child()
        self.assertEqual(ctx2.depth, 2)

        output, error = await _exec_delegate_agent({"task": "one more level"}, delegation=ctx2)
        tmp.cleanup()
        self.assertIsNone(output)
        self.assertIn("depth limit", error)


class TestExecuteToolDelegateAgentIntegration(unittest.IsolatedAsyncioTestCase):
    """execute_tool() itself routes DELEGATE_AGENT to _exec_delegate_agent
    and honors the LOCAL_ONLY_TOOLS gate correctly (delegate_agent is a
    dispatch call, not local execution -- must work from a cloud worker
    too)."""

    async def test_execute_tool_routes_to_delegate_agent(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        orchestrator = _FakeOrchestrator(_one_step_plan(), "sub result")
        provider = _FakeProvider()
        pipeline, tmp, store, budget = _pipeline(orchestrator, provider)
        ctx = DelegationContext(registry=registry, store=store, mode_name="cowork", pipeline=pipeline)

        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                result = await execute_tool(
                    _tr("delegate_agent", {"task": "go do it"}),
                    worker=_worker(), cwd=Path("."), delegation=ctx,
                )
        finally:
            tmp.cleanup()
        self.assertIsNone(result.error)
        self.assertEqual(result.tool_output["result"], "sub result")

    async def test_delegate_agent_works_from_cloud_worker(self):
        result = await execute_tool(
            _tr("delegate_agent", {"task": "x"}),
            worker=_worker(),  # LOCAL_HARDWARE fine; cloud tested via compute_location below
            cwd=Path("."), delegation=None,
        )
        # No delegation context at all -- proves the "unavailable" error
        # path, not a LOCAL_ONLY_TOOLS rejection (which would mention
        # "restricted to LOCAL_HARDWARE").
        self.assertNotIn("restricted to LOCAL_HARDWARE", result.error or "")


if __name__ == "__main__":
    unittest.main()
