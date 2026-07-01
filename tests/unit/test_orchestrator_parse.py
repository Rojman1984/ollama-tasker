"""
Unit tests -- shared plan parsing (tasker/orchestrator/_parse.py)

Regression coverage for the bug where a single unrecognized capability
string inside an otherwise-valid model plan response caused parse_plan()
to silently discard the ENTIRE plan in favor of NanoOrchestrator's generic
fallback template, with no logging and no way for a caller to detect it.
"""
import json
import unittest

from tasker.orchestrator._parse import CAPABILITY_ALIASES, parse_plan
from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
from tasker.workers.base import (
    Capability,
    ClassifierResult,
    ExecutionPlan,
    TaskType,
)


def _classifier(task_type: TaskType = TaskType.CODING) -> ClassifierResult:
    return ClassifierResult(
        task_type=task_type,
        complexity_score=0.5,
        required_capabilities={Capability.TOOL_USE, Capability.CODE},
        suggested_workers=[],
        estimated_duration_s=30.0,
    )


def _mock_call(response: str):
    async def _call(system: str, user: str) -> str:
        return response
    return _call


class TestParsePlan(unittest.TestCase):

    def test_valid_plan_all_capabilities_recognized(self):
        raw = json.dumps([
            {"description": "analyze", "role": "thinker", "capabilities": ["tool_use", "code"]},
            {"description": "implement", "role": "worker", "capabilities": ["tool_use", "code"]},
        ])
        with self.assertNoLogs("tasker.orchestrator._parse", level="WARNING"):
            plan = parse_plan("fix the bug", raw)
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertFalse(plan.used_fallback)
        self.assertEqual(len(plan.steps), 2)

    def test_one_step_unrecognized_capability_preserves_plan(self):
        raw = json.dumps([
            {"description": "analyze", "role": "thinker", "capabilities": ["tool_use"]},
            {"description": "implement", "role": "worker", "capabilities": ["totally_made_up_capability"]},
            {"description": "verify", "role": "verifier", "capabilities": ["tool_use"]},
        ])
        with self.assertLogs("tasker.orchestrator._parse", level="WARNING") as cm:
            plan = parse_plan("fix the bug", raw)

        self.assertIsInstance(plan, ExecutionPlan)
        self.assertFalse(plan.used_fallback)
        self.assertEqual(len(plan.steps), 3)
        self.assertEqual(plan.steps[0].description, "analyze")
        self.assertEqual(plan.steps[1].description, "implement")
        self.assertEqual(plan.steps[2].description, "verify")
        # The bad step still gets a usable capability set (TOOL_USE default).
        self.assertIn(Capability.TOOL_USE, plan.steps[1].required_capabilities)

        log_output = "\n".join(cm.output)
        self.assertIn("totally_made_up_capability", log_output)
        self.assertIn("1", log_output)  # step index

    def test_alias_capability_silently_corrected(self):
        self.assertIn("tool_execution", CAPABILITY_ALIASES)
        raw = json.dumps([
            {"description": "run tool", "role": "worker", "capabilities": ["tool_execution"]},
        ])
        with self.assertNoLogs("tasker.orchestrator._parse", level="WARNING"):
            plan = parse_plan("task", raw)
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 1)
        self.assertIn(Capability.TOOL_USE, plan.steps[0].required_capabilities)

    def test_all_steps_zero_valid_capabilities_default_to_tool_use(self):
        raw = json.dumps([
            {"description": "step 0", "role": "worker", "capabilities": ["bogus_one"]},
            {"description": "step 1", "role": "worker", "capabilities": ["bogus_two"]},
        ])
        with self.assertLogs("tasker.orchestrator._parse", level="WARNING") as cm:
            plan = parse_plan("task", raw)

        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].required_capabilities, {Capability.TOOL_USE})
        self.assertEqual(plan.steps[1].required_capabilities, {Capability.TOOL_USE})
        self.assertEqual(len(cm.output), 2)

    def test_malformed_json_returns_none_with_warning(self):
        with self.assertLogs("tasker.orchestrator._parse", level="WARNING") as cm:
            plan = parse_plan("task", "this is not json at all")
        self.assertIsNone(plan)
        self.assertIn("this is not json at all", "\n".join(cm.output))

    def test_empty_array_returns_none(self):
        plan = parse_plan("task", "[]")
        self.assertIsNone(plan)


class TestSingleLLMOrchestratorUsedFallback(unittest.IsolatedAsyncioTestCase):

    async def test_valid_plan_used_fallback_false(self):
        raw = json.dumps([
            {"description": "step", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_mock_call(raw))
        plan = await orc.plan("task", _classifier(), [])
        self.assertFalse(plan.used_fallback)

    async def test_one_bad_capability_does_not_trigger_fallback(self):
        raw = json.dumps([
            {"description": "step one", "role": "worker", "capabilities": ["tool_use", "code"]},
            {"description": "step two", "role": "worker", "capabilities": ["not_a_real_capability"]},
        ])
        orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_mock_call(raw))
        with self.assertLogs("tasker.orchestrator._parse", level="WARNING"):
            plan = await orc.plan("task", _classifier(), [])
        self.assertFalse(plan.used_fallback)
        self.assertEqual(len(plan.steps), 2)

    async def test_malformed_response_falls_back_with_flag_set(self):
        orc = SingleLLMOrchestrator(model_id="qwen3:1.7b", call_model=_mock_call("not json"))
        with self.assertLogs("tasker.orchestrator._parse", level="WARNING") as cm:
            plan = await orc.plan("write a function", _classifier(TaskType.CODING), [])
        self.assertTrue(plan.used_fallback)
        self.assertGreater(len(plan.steps), 0)
        self.assertIn("not json", "\n".join(cm.output))


if __name__ == "__main__":
    unittest.main()
