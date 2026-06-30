"""
Unit tests -- DualLLMOrchestrator Tier 2 (tasker/orchestrator/tier2_dual.py)
Phase 6 -- SDD Section 5.3
"""
import json
import unittest

from tasker.orchestrator.tier2_dual import DualLLMOrchestrator
from tasker.workers.base import (
    AgentRole,
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


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _classifier(task_type: TaskType = TaskType.CODING, complexity: float = 0.5) -> ClassifierResult:
    return ClassifierResult(
        task_type=task_type,
        complexity_score=complexity,
        required_capabilities={Capability.TOOL_USE, Capability.CODE},
        suggested_workers=[],
        estimated_duration_s=30.0,
    )


def _result(output: str, worker_id: str = "w1") -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id=worker_id,
        status=WorkerStatus.SUCCESS,
        output=output,
        tool_results=[],
        usage=ModelUsage(input_tokens=50, output_tokens=100, cost_usd=0.0),
        duration_ms=500,
    )


def _failed_result(reason: str = "timeout") -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id="w1",
        status=WorkerStatus.FAILED,
        output=None,
        tool_results=[],
        usage=ModelUsage(input_tokens=0, output_tokens=0, cost_usd=0.0),
        duration_ms=100,
        reason=reason,
    )


def _mock_call(response: str):
    async def _call(system: str, user: str) -> str:
        return response
    return _call


def _make_dual(plan_response: str, synth_response: str) -> DualLLMOrchestrator:
    return DualLLMOrchestrator(
        planner_model_id="qwen3:8b",
        synthesizer_model_id="llama3.1:8b",
        call_planner=_mock_call(plan_response),
        call_synthesizer=_mock_call(synth_response),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestDualLLMOrchestrator(unittest.IsolatedAsyncioTestCase):

    # ------------------------------------------------------------------ #
    # plan() uses call_planner
    # ------------------------------------------------------------------ #

    async def test_plan_parses_valid_json(self):
        plan_json = json.dumps([
            {"description": "analyse", "role": "thinker", "capabilities": ["tool_use", "reasoning"]},
            {"description": "execute", "role": "worker", "capabilities": ["tool_use", "code"]},
        ])
        orc = _make_dual(plan_json, "synth output")
        plan = await orc.plan("refactor codebase", _classifier(), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].role, AgentRole.THINKER)
        self.assertEqual(plan.steps[1].role, AgentRole.WORKER)

    async def test_plan_falls_back_to_nano_on_bad_json(self):
        orc = _make_dual("not json", "synth")
        plan = await orc.plan("task", _classifier(TaskType.CODING), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertGreater(len(plan.steps), 0)

    async def test_plan_preserves_original_task(self):
        plan_json = json.dumps([
            {"description": "step", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_dual(plan_json, "synth")
        plan = await orc.plan("my dual task", _classifier(), [])
        self.assertEqual(plan.original_task, "my dual task")

    async def test_plan_injects_tool_use(self):
        plan_json = json.dumps([
            {"description": "do it", "role": "worker", "capabilities": ["code"]},
        ])
        orc = _make_dual(plan_json, "synth")
        plan = await orc.plan("task", _classifier(), [])
        self.assertIn(Capability.TOOL_USE, plan.steps[0].required_capabilities)

    async def test_plan_dependency_chain(self):
        plan_json = json.dumps([
            {"description": "step 0", "role": "thinker", "capabilities": ["tool_use"]},
            {"description": "step 1", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_dual(plan_json, "synth")
        plan = await orc.plan("task", _classifier(), [])
        self.assertEqual(plan.steps[0].depends_on, [])
        self.assertEqual(plan.steps[1].depends_on, [0])

    # ------------------------------------------------------------------ #
    # synthesize() uses call_synthesizer (NOT call_planner)
    # ------------------------------------------------------------------ #

    async def test_synthesize_uses_synthesizer_not_planner(self):
        planner_calls: list[str] = []
        synth_calls:   list[str] = []

        async def _planner(system: str, user: str) -> str:
            planner_calls.append(user)
            return "planner called"

        async def _synthesizer(system: str, user: str) -> str:
            synth_calls.append(user)
            return "final synthesis"

        orc = DualLLMOrchestrator(
            planner_model_id="p",
            synthesizer_model_id="s",
            call_planner=_planner,
            call_synthesizer=_synthesizer,
        )
        output = await orc.synthesize("build a widget", [_result("A"), _result("B")])
        self.assertEqual(output, "final synthesis")
        self.assertEqual(len(planner_calls), 0)          # planner NOT called during synthesis
        self.assertEqual(len(synth_calls), 1)

    async def test_synthesize_passes_task_and_outputs(self):
        captured: list[str] = []

        async def _synthesizer(system: str, user: str) -> str:
            captured.append(user)
            return "done"

        orc = DualLLMOrchestrator(
            planner_model_id="p",
            synthesizer_model_id="s",
            call_planner=_mock_call("[]"),
            call_synthesizer=_synthesizer,
        )
        await orc.synthesize("write a report", [_result("part one"), _result("part two")])
        self.assertTrue(any("write a report" in u for u in captured))
        self.assertTrue(any("part one" in u for u in captured))

    # ------------------------------------------------------------------ #
    # should_retry() uses call_planner
    # ------------------------------------------------------------------ #

    async def test_should_retry_uses_planner(self):
        planner_calls: list[str] = []
        synth_calls:   list[str] = []

        retry_json = json.dumps({"should_retry": True, "reassign": False, "reason": "transient"})

        async def _planner(system: str, user: str) -> str:
            planner_calls.append(user)
            return retry_json

        async def _synthesizer(system: str, user: str) -> str:
            synth_calls.append(user)
            return "synthesized"

        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        plan_orc = DualLLMOrchestrator("p", "s", _mock_call(plan_json), _mock_call("synth"))
        plan = await plan_orc.plan("task", _classifier(), [])

        orc = DualLLMOrchestrator("p", "s", _planner, _synthesizer)
        decision = await orc.should_retry(plan, _failed_result())
        self.assertTrue(decision.should_retry)
        self.assertEqual(len(planner_calls), 1)
        self.assertEqual(len(synth_calls), 0)   # synthesizer NOT called for retry

    async def test_should_retry_falls_back_on_malformed(self):
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        plan = await DualLLMOrchestrator("p", "s", _mock_call(plan_json), _mock_call("")).plan(
            "task", _classifier(), []
        )
        orc = _make_dual("cannot decide", "synth")
        decision = await orc.should_retry(plan, _failed_result())
        self.assertFalse(decision.should_retry)
        self.assertIsInstance(decision.reason, str)


if __name__ == "__main__":
    unittest.main()
