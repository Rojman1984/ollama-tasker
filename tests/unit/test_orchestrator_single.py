"""
Unit tests -- SingleLLMOrchestrator Tier 1 (tasker/orchestrator/tier1_single.py)
Phase 3 -- SDD Section 5.3
"""
import json
import unittest

from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
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
    """Returns a call_model coroutine that always returns `response`."""
    async def _call(system: str, user: str) -> str:
        return response
    return _call


def _make_orc(response: str) -> SingleLLMOrchestrator:
    return SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_mock_call(response))


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestSingleLLMOrchestrator(unittest.IsolatedAsyncioTestCase):

    # ------------------------------------------------------------------ #
    # plan()
    # ------------------------------------------------------------------ #

    async def test_plan_parses_valid_json_response(self):
        plan_json = json.dumps([
            {"description": "analyze the code", "role": "thinker", "capabilities": ["tool_use", "code"]},
            {"description": "write the fix", "role": "worker", "capabilities": ["tool_use", "code"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("fix the bug", _classifier(), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].description, "analyze the code")
        self.assertEqual(plan.steps[0].role, AgentRole.THINKER)
        self.assertEqual(plan.steps[1].role, AgentRole.WORKER)

    async def test_plan_steps_all_pending(self):
        plan_json = json.dumps([
            {"description": "step one", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("task", _classifier(), [])
        self.assertEqual(plan.steps[0].status, StepStatus.PENDING)

    async def test_plan_injects_tool_use_if_missing(self):
        plan_json = json.dumps([
            {"description": "do something", "role": "worker", "capabilities": ["code"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("task", _classifier(), [])
        self.assertIn(Capability.TOOL_USE, plan.steps[0].required_capabilities)

    async def test_plan_falls_back_to_nano_on_malformed_json(self):
        orc = _make_orc("this is not json at all")
        cr = _classifier(TaskType.CODING)
        plan = await orc.plan("write a function", cr, [])
        # NanoOrchestrator fallback produces 2 steps for CODING
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertGreater(len(plan.steps), 0)

    async def test_plan_recovers_via_reask_before_falling_back(self):
        calls = []
        good_plan = json.dumps([
            {"description": "create the file", "role": "worker", "capabilities": ["tool_use"]},
        ])

        async def flaky_call(system: str, user: str) -> str:
            calls.append(user)
            return "not valid json" if len(calls) == 1 else good_plan

        orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=flaky_call)
        plan = await orc.plan("create a file", _classifier(TaskType.CONVERSATIONAL), [])
        self.assertFalse(plan.used_fallback)
        self.assertEqual(plan.steps[0].description, "create the file")
        self.assertEqual(len(calls), 2)   # initial call + exactly one re-ask

    async def test_plan_falls_back_to_nano_on_empty_array(self):
        orc = _make_orc("[]")
        plan = await orc.plan("task", _classifier(TaskType.RESEARCH), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertGreater(len(plan.steps), 0)

    async def test_plan_preserves_original_task(self):
        plan_json = json.dumps([
            {"description": "do it", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("my specific task", _classifier(), [])
        self.assertEqual(plan.original_task, "my specific task")

    async def test_plan_dependency_chain(self):
        plan_json = json.dumps([
            {"description": "step 0", "role": "thinker", "capabilities": ["tool_use"]},
            {"description": "step 1", "role": "worker", "capabilities": ["tool_use"]},
            {"description": "step 2", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("task", _classifier(), [])
        self.assertEqual(plan.steps[0].depends_on, [])
        self.assertEqual(plan.steps[1].depends_on, [0])
        self.assertEqual(plan.steps[2].depends_on, [0, 1])

    # ------------------------------------------------------------------ #
    # synthesize()
    # ------------------------------------------------------------------ #

    async def test_synthesize_returns_model_response(self):
        orc = _make_orc("Here is the final answer.")
        output = await orc.synthesize("original task", [_result("part one"), _result("part two")])
        self.assertEqual(output, "Here is the final answer.")

    async def test_synthesize_called_with_worker_outputs(self):
        captured: list[str] = []

        async def _recording_call(system: str, user: str) -> str:
            captured.append(user)
            return "synthesized"

        orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_recording_call)
        await orc.synthesize("build a widget", [_result("output A"), _result("output B")])
        self.assertTrue(any("output A" in u for u in captured))
        self.assertTrue(any("build a widget" in u for u in captured))

    # ------------------------------------------------------------------ #
    # should_retry()
    # ------------------------------------------------------------------ #

    async def test_should_retry_parses_true_response(self):
        retry_json = json.dumps({"should_retry": True, "reassign": False, "reason": "transient error"})
        orc = _make_orc(retry_json)
        cr = _classifier()
        plan_json = json.dumps([
            {"description": "step", "role": "worker", "capabilities": ["tool_use"]},
        ])
        plan_orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_mock_call(plan_json))
        plan = await plan_orc.plan("task", cr, [])

        retry_orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_mock_call(retry_json))
        decision = await retry_orc.should_retry(plan, _failed_result())
        self.assertTrue(decision.should_retry)
        self.assertFalse(decision.reassign)
        self.assertEqual(decision.reason, "transient error")

    async def test_should_retry_parses_false_response(self):
        retry_json = json.dumps({"should_retry": False, "reassign": True, "reason": "permanent failure"})
        orc = _make_orc(retry_json)
        cr = _classifier()
        plan_json = json.dumps([
            {"description": "step", "role": "worker", "capabilities": ["tool_use"]},
        ])
        plan = await SingleLLMOrchestrator(
            model_id="qwen3:1.7b", call_model=_mock_call(plan_json)
        ).plan("task", cr, [])

        decision = await orc.should_retry(plan, _failed_result())
        self.assertFalse(decision.should_retry)
        self.assertTrue(decision.reassign)

    async def test_should_retry_falls_back_on_malformed_response(self):
        orc = _make_orc("cannot decide")
        plan_json = json.dumps([
            {"description": "step", "role": "worker", "capabilities": ["tool_use"]},
        ])
        plan = await SingleLLMOrchestrator(
            model_id="qwen3:1.7b", call_model=_mock_call(plan_json)
        ).plan("task", _classifier(), [])

        decision = await orc.should_retry(plan, _failed_result())
        self.assertFalse(decision.should_retry)
        self.assertIsInstance(decision.reason, str)

    # ------------------------------------------------------------------ #
    # mode_name threading (SDD 5.1a research-mode grounding)
    # ------------------------------------------------------------------ #

    async def test_mode_name_reaches_plan_prompt(self):
        captured = []

        async def recording_call(system, user):
            captured.append(user)
            return json.dumps([{"description": "search for x", "role": "worker", "capabilities": ["tool_use"]}])

        orc = SingleLLMOrchestrator(model_id="m", call_model=recording_call, mode_name="research")
        await orc.plan("task", _classifier(), [])
        self.assertIn("GROUNDING REQUIREMENT", captured[0])

    async def test_mode_name_reaches_synthesize_prompt(self):
        captured = []

        async def recording_call(system, user):
            captured.append(user)
            return "answer"

        orc = SingleLLMOrchestrator(model_id="m", call_model=recording_call, mode_name="research")
        await orc.synthesize("task", [_result("output")])
        self.assertIn("GROUNDING REQUIREMENT", captured[0])

    async def test_default_mode_name_none_no_grounding_text(self):
        captured = []

        async def recording_call(system, user):
            captured.append(user)
            return "answer"

        orc = SingleLLMOrchestrator(model_id="m", call_model=recording_call)
        await orc.synthesize("task", [_result("output")])
        self.assertNotIn("GROUNDING", captured[0])


if __name__ == "__main__":
    unittest.main()
