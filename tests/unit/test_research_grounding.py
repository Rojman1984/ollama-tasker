"""
Unit tests -- RESEARCH mode grounding enforcement (SDD 5.1a,
tasker/runtime/dispatch.py). Live bug: a research task fabricated an
entire model comparison and a benchmark statistic with zero tool calls.

Covers _search_backend_configured(), _enforce_research_grounding()
(plan-injection backstop), _apply_research_synthesis_honesty(), and the
end-to-end wiring into _run_task()/_execute_steps() with a fake
orchestrator + fake provider (no real HTTP/model calls).
"""
import dataclasses
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tasker.modes.base import ModeConfigurator
from tasker.runtime.dispatch import (
    _apply_research_synthesis_honesty,
    _enforce_research_grounding,
    _run_task,
    _search_backend_configured,
)
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import CheckpointStore
from tasker.session.concurrency import OllamaCloudConcurrencyManager
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
    RoutingPolicy,
    StepStatus,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerToolResult,
)
from tasker.workers.providers.base import WorkerProviderBase
from tasker.workers.registry import WorkerRegistry


def _plan(steps: list[PlanStep], original_task: str = "compare model A and model B") -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p1",
        original_task=original_task,
        steps=steps,
        dependency_graph={s.index: s.depends_on for s in steps},
    )


def _step(index, caps, depends_on=None, description="a step") -> PlanStep:
    return PlanStep(
        index=index, description=description, role=AgentRole.WORKER,
        required_capabilities=set(caps), depends_on=depends_on or [],
        status=StepStatus.PENDING,
    )


class TestSearchBackendConfigured(unittest.TestCase):

    def test_true_when_key_set(self):
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "x"}):
            self.assertTrue(_search_backend_configured())

    def test_false_when_unset(self):
        with mock.patch.dict("os.environ", {}, clear=True):
            self.assertFalse(_search_backend_configured())

    def test_false_when_empty_string(self):
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": ""}):
            self.assertFalse(_search_backend_configured())


class TestEnforceResearchGrounding(unittest.TestCase):

    def test_non_research_mode_untouched(self):
        plan = _plan([_step(0, {Capability.TOOL_USE})])
        result = _enforce_research_grounding(plan, "chat", search_configured=True)
        self.assertIs(result, plan)

    def test_no_search_backend_untouched_even_in_research(self):
        plan = _plan([_step(0, {Capability.TOOL_USE})])
        result = _enforce_research_grounding(plan, "research", search_configured=False)
        self.assertIs(result, plan)

    def test_plan_already_has_search_step_untouched(self):
        plan = _plan([_step(0, {Capability.TOOL_USE, Capability.SEARCH})])
        result = _enforce_research_grounding(plan, "research", search_configured=True)
        self.assertIs(result, plan)

    def test_injects_retrieval_step_when_missing(self):
        plan = _plan([_step(0, {Capability.TOOL_USE}, description="compare A and B")])
        result = _enforce_research_grounding(plan, "research", search_configured=True)
        self.assertEqual(len(result.steps), 2)
        self.assertIn(Capability.SEARCH, result.steps[0].required_capabilities)
        self.assertIn(Capability.TOOL_USE, result.steps[0].required_capabilities)
        self.assertEqual(result.steps[0].index, 0)

    def test_injected_step_description_mentions_original_task(self):
        plan = _plan([_step(0, {Capability.TOOL_USE})], original_task="compare A and B")
        result = _enforce_research_grounding(plan, "research", search_configured=True)
        self.assertIn("compare A and B", result.steps[0].description)

    def test_original_steps_reindexed_and_dependencies_shifted(self):
        plan = _plan([
            _step(0, {Capability.TOOL_USE}, depends_on=[]),
            _step(1, {Capability.TOOL_USE}, depends_on=[0]),
        ])
        result = _enforce_research_grounding(plan, "research", search_configured=True)
        self.assertEqual([s.index for s in result.steps], [0, 1, 2])
        self.assertEqual(result.steps[1].depends_on, [])   # was step 0, now step 1, no deps
        self.assertEqual(result.steps[2].depends_on, [1])  # was depends_on=[0], now [1]

    def test_dependency_graph_matches_reindexed_steps(self):
        plan = _plan([_step(0, {Capability.TOOL_USE})])
        result = _enforce_research_grounding(plan, "research", search_configured=True)
        for step in result.steps:
            self.assertEqual(result.dependency_graph[step.index], step.depends_on)

    def test_original_plan_object_not_mutated(self):
        plan = _plan([_step(0, {Capability.TOOL_USE})])
        original_step_count = len(plan.steps)
        _enforce_research_grounding(plan, "research", search_configured=True)
        self.assertEqual(len(plan.steps), original_step_count)


class TestApplyResearchSynthesisHonesty(unittest.TestCase):

    def _result(self, tool_results):
        return WorkerResult(
            task_id="t", worker_id="w", status=WorkerStatus.SUCCESS, output="x",
            tool_results=tool_results, usage=ModelUsage(0, 0, 0.0), duration_ms=0,
        )

    def _tr(self, name):
        return WorkerToolResult(tool_name=name, tool_input={}, tool_output="ok", error=None, duration_ms=1)

    def test_non_research_mode_untouched(self):
        output = _apply_research_synthesis_honesty("A fact.", "chat", [self._result([])])
        self.assertEqual(output, "A fact.")

    def test_research_mode_no_retrieval_anywhere_flagged(self):
        output = _apply_research_synthesis_honesty(
            "Model A beats Model B by 12%.", "research", [self._result([]), self._result([])],
        )
        self.assertTrue(output.startswith("[unverified"))

    def test_research_mode_retrieval_in_any_step_grounds_synthesis(self):
        results = [self._result([]), self._result([self._tr("web_search")])]
        output = _apply_research_synthesis_honesty("Model A beats Model B by 12%.", "research", results)
        self.assertEqual(output, "Model A beats Model B by 12%.")


class _FakeOrchestrator:
    def __init__(self, plan, synth_output):
        self._plan = plan
        self._synth_output = synth_output
        self.plan_calls = []
        self.synth_calls = []

    async def plan(self, task, classifier_output, workers):
        self.plan_calls.append(task)
        return self._plan

    async def synthesize(self, task, results):
        self.synth_calls.append(results)
        return self._synth_output


class _FakeProvider(WorkerProviderBase):
    def __init__(self, tool_results=None):
        self._tool_results = tool_results or []
        self.calls = 0

    def supports(self, worker):
        return True

    async def health_check(self, worker):
        return True

    async def execute(self, task, worker):
        self.calls += 1
        return WorkerResult(
            task_id=task.task_id, worker_id=worker.id, status=WorkerStatus.SUCCESS,
            output="a plausible-sounding claim", tool_results=self._tool_results,
            usage=ModelUsage(10, 10, 0.0), duration_ms=5,
        )


def _worker(worker_id="w1") -> WorkerManifest:
    return WorkerManifest(
        id=worker_id, provider=ProviderType.OLLAMA, model_id="test:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE, Capability.SEARCH},
        tool_protocol=ToolProtocol.NATIVE, context_window=8192,
        cost_input=0.0, cost_output=0.0, ollama_usage_level=None,
        latency_class=LatencyClass.FAST, available=True, requires_gpu=False, vram_mb=None,
    )


def _pipeline(orchestrator, provider):
    config = ModeConfigurator().build("tier1_tasker", "research")
    budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
    tmp = tempfile.TemporaryDirectory()
    store = CheckpointStore(Path(tmp.name))
    session_mgr = SessionManager(budget, store, LogNotifier(), auto_resume=False)
    concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
    provider_map = {ProviderType.OLLAMA: provider}
    pipeline = ("tier1_tasker", config, budget, session_mgr, concurrency_mgr, provider_map, orchestrator)
    return pipeline, tmp, store


class TestRunTaskResearchGroundingEndToEnd(unittest.IsolatedAsyncioTestCase):

    async def test_plan_without_search_step_gets_one_injected_when_backend_configured(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        bare_plan = _plan([_step(0, {Capability.TOOL_USE}, description="compare A and B")])
        orchestrator = _FakeOrchestrator(bare_plan, "A fact with no source.")
        provider = _FakeProvider(tool_results=[])
        pipeline, tmp, store = _pipeline(orchestrator, provider)

        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline), \
                 mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}):
                await _run_task("compare A and B", "research", registry, store)
        finally:
            tmp.cleanup()

        # two steps actually executed: the injected retrieval step + the original
        self.assertEqual(provider.calls, 2)

    async def test_final_synthesis_flagged_when_no_retrieval_ever_happened(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        bare_plan = _plan([_step(0, {Capability.TOOL_USE, Capability.SEARCH}, description="search")])
        orchestrator = _FakeOrchestrator(bare_plan, "Model A beats Model B by 12%.")
        provider = _FakeProvider(tool_results=[])   # worker never actually calls a tool
        pipeline, tmp, store = _pipeline(orchestrator, provider)

        printed = []
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline), \
                 mock.patch.dict("os.environ", {}, clear=True), \
                 mock.patch("builtins.print", side_effect=lambda *a: printed.append(" ".join(str(x) for x in a))):
                await _run_task("compare A and B", "research", registry, store)
        finally:
            tmp.cleanup()

        self.assertTrue(any("[unverified" in line for line in printed))

    async def test_no_flag_when_a_real_retrieval_call_backs_the_claim(self):
        registry = WorkerRegistry()
        registry.register(_worker())
        bare_plan = _plan([_step(0, {Capability.TOOL_USE, Capability.SEARCH}, description="search")])
        orchestrator = _FakeOrchestrator(bare_plan, "Model A beats Model B by 12%.")
        provider = _FakeProvider(tool_results=[
            WorkerToolResult(tool_name="web_search", tool_input={}, tool_output="ok", error=None, duration_ms=1),
        ])
        pipeline, tmp, store = _pipeline(orchestrator, provider)

        printed = []
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline), \
                 mock.patch("builtins.print", side_effect=lambda *a: printed.append(" ".join(str(x) for x in a))):
                await _run_task("compare A and B", "research", registry, store)
        finally:
            tmp.cleanup()

        self.assertFalse(any("[unverified" in line for line in printed))


if __name__ == "__main__":
    unittest.main()
