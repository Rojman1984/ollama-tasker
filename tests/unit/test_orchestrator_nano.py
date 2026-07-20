"""
Unit tests -- NanoOrchestrator Tier 0 (tasker/orchestrator/tier0_rules.py)
Phase 3 -- SDD Section 5.3
"""
import unittest

from tasker.orchestrator.tier0_rules import NanoOrchestrator
from tasker.workers.base import (
    Capability,
    ClassifierResult,
    ExecutionPlan,
    FallbackHint,
    ModelUsage,
    StepStatus,
    TaskType,
    WorkerResult,
    WorkerStatus,
)


def _classifier(task_type: TaskType, complexity: float = 0.5) -> ClassifierResult:
    return ClassifierResult(
        task_type=task_type,
        complexity_score=complexity,
        required_capabilities={Capability.TOOL_USE},
        suggested_workers=[],
        estimated_duration_s=10.0,
    )


def _result(output: str, worker_id: str = "w1") -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id=worker_id,
        status=WorkerStatus.SUCCESS,
        output=output,
        tool_results=[],
        usage=ModelUsage(input_tokens=10, output_tokens=20, cost_usd=0.0),
        duration_ms=100,
    )


def _failed_result() -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id="w1",
        status=WorkerStatus.FAILED,
        output=None,
        tool_results=[],
        usage=ModelUsage(input_tokens=0, output_tokens=0, cost_usd=0.0),
        duration_ms=50,
        reason="provider error",
    )


class TestNanoOrchestrator(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        self.orc = NanoOrchestrator()

    # ------------------------------------------------------------------ #
    # plan()
    # ------------------------------------------------------------------ #

    async def test_plan_returns_execution_plan(self):
        cr = _classifier(TaskType.CONVERSATIONAL)
        plan = await self.orc.plan("say hello", cr, [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.original_task, "say hello")
        self.assertGreater(len(plan.steps), 0)
        self.assertIsNotNone(plan.plan_id)

    async def test_plan_makes_no_llm_calls(self):
        # NanoOrchestrator must work with zero workers — it never calls any model.
        cr = _classifier(TaskType.CODING)
        plan = await self.orc.plan("write a sort function", cr, available_workers=[])
        self.assertIsInstance(plan, ExecutionPlan)

    async def test_conversational_produces_one_step(self):
        cr = _classifier(TaskType.CONVERSATIONAL)
        plan = await self.orc.plan("what time is it?", cr, [])
        self.assertEqual(len(plan.steps), 1)

    async def test_coding_produces_two_steps(self):
        cr = _classifier(TaskType.CODING)
        plan = await self.orc.plan("implement binary search", cr, [])
        self.assertEqual(len(plan.steps), 2)

    async def test_research_produces_three_steps(self):
        cr = _classifier(TaskType.RESEARCH)
        plan = await self.orc.plan("research quantum computing", cr, [])
        self.assertEqual(len(plan.steps), 3)

    async def test_reasoning_produces_two_steps(self):
        cr = _classifier(TaskType.REASONING)
        plan = await self.orc.plan("solve this logic puzzle", cr, [])
        self.assertEqual(len(plan.steps), 2)

    async def test_steps_all_start_pending(self):
        cr = _classifier(TaskType.CODING)
        plan = await self.orc.plan("task", cr, [])
        for step in plan.steps:
            self.assertEqual(step.status, StepStatus.PENDING)

    async def test_steps_depend_on_all_previous(self):
        cr = _classifier(TaskType.RESEARCH)
        plan = await self.orc.plan("research", cr, [])
        # step 0 depends on nothing, step 1 depends on [0], step 2 depends on [0,1]
        self.assertEqual(plan.steps[0].depends_on, [])
        self.assertEqual(plan.steps[1].depends_on, [0])
        self.assertEqual(plan.steps[2].depends_on, [0, 1])

    async def test_dependency_graph_matches_steps(self):
        cr = _classifier(TaskType.RESEARCH)
        plan = await self.orc.plan("research", cr, [])
        for step in plan.steps:
            self.assertEqual(plan.dependency_graph[step.index], step.depends_on)

    async def test_step_description_carries_original_task_text(self):
        # Live bug: a fallback plan's generic template description ("Answer
        # the task") gave narrow_bundle_to_step() no keyword signal of its
        # own, relying entirely on a second-chance match against the raw
        # task text threaded through by the caller. The step description
        # itself must now carry the user's real wording.
        task = "create a text file with hello from tasker! and provide the path"
        cr = _classifier(TaskType.CONVERSATIONAL)
        plan = await self.orc.plan(task, cr, [])
        self.assertIn(task, plan.steps[0].description)

    async def test_multi_step_template_embeds_task_in_every_step(self):
        task = "implement binary search"
        cr = _classifier(TaskType.CODING)
        plan = await self.orc.plan(task, cr, [])
        for step in plan.steps:
            self.assertIn(task, step.description)

    async def test_all_steps_require_tool_use(self):
        for task_type in TaskType:
            cr = _classifier(task_type)
            plan = await self.orc.plan("task", cr, [])
            for step in plan.steps:
                self.assertIn(Capability.TOOL_USE, step.required_capabilities,
                              f"{task_type}: step {step.index} missing TOOL_USE")

    # ------------------------------------------------------------------ #
    # synthesize()
    # ------------------------------------------------------------------ #

    async def test_synthesize_merges_results(self):
        results = [_result("part one"), _result("part two")]
        output = await self.orc.synthesize("original task", results)
        self.assertIn("part one", output)
        self.assertIn("part two", output)

    async def test_synthesize_empty_results_returns_empty_string(self):
        output = await self.orc.synthesize("task", [])
        self.assertEqual(output, "")

    async def test_synthesize_none_outputs_skipped(self):
        results = [_failed_result(), _result("good output")]
        output = await self.orc.synthesize("task", results)
        self.assertIn("good output", output)

    # ------------------------------------------------------------------ #
    # should_retry()
    # ------------------------------------------------------------------ #

    async def test_should_retry_returns_false(self):
        cr = _classifier(TaskType.CONVERSATIONAL)
        plan = await self.orc.plan("task", cr, [])
        decision = await self.orc.should_retry(plan, _failed_result())
        self.assertFalse(decision.should_retry)
        self.assertFalse(decision.reassign)
        self.assertIsInstance(decision.reason, str)


if __name__ == "__main__":
    unittest.main()
