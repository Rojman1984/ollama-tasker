"""
Unit tests -- plan-parse resilience ladder (tasker/orchestrator/_parse.py).

Live bug: a cowork planner response failed to parse, the run fell
straight to NanoOrchestrator, and lost the user's real instruction. Fix
(1) of that session's three-part fix: before falling back, try a
tolerant text repair (no model call) and then one re-ask (one extra
model call) before giving up.
"""
import json
import unittest

from tasker.orchestrator._parse import _plan_parse_error, _tolerant_repair, plan_with_repair
from tasker.workers.base import ExecutionPlan


_VALID_PLAN = json.dumps([
    {"description": "do the thing", "role": "worker", "capabilities": ["tool_use"]},
])


class TestTolerantRepair(unittest.TestCase):

    def test_strips_markdown_code_fence(self):
        wrapped = f"```json\n{_VALID_PLAN}\n```"
        self.assertEqual(_tolerant_repair(wrapped), _VALID_PLAN)

    def test_removes_trailing_comma_before_closing_bracket(self):
        damaged = '[{"description": "x", "role": "worker", "capabilities": ["tool_use"]},]'
        repaired = _tolerant_repair(damaged)
        data = json.loads(repaired)  # raises if the trailing comma wasn't removed
        self.assertEqual(len(data), 1)

    def test_converts_single_quoted_tokens_to_double_quotes(self):
        damaged = "[{'description': 'x', 'role': 'worker', 'capabilities': ['tool_use']}]"
        repaired = _tolerant_repair(damaged)
        data = json.loads(repaired)
        self.assertEqual(data[0]["description"], "x")

    def test_leaves_already_valid_json_unchanged_in_content(self):
        repaired = _tolerant_repair(_VALID_PLAN)
        self.assertEqual(json.loads(repaired), json.loads(_VALID_PLAN))


class TestPlanParseError(unittest.TestCase):

    def test_reports_invalid_json_syntax(self):
        msg = _plan_parse_error("not json at all")
        self.assertIn("invalid JSON", msg)

    def test_reports_non_array_top_level(self):
        msg = _plan_parse_error('{"description": "x"}')
        self.assertIn("array", msg)

    def test_reports_empty_array(self):
        msg = _plan_parse_error("[]")
        self.assertIn("empty", msg)


class TestPlanWithRepair(unittest.IsolatedAsyncioTestCase):

    async def test_valid_raw_parses_without_any_model_call(self):
        calls = []

        async def call_model(system, user):
            calls.append(user)
            return "should never be called"

        plan = await plan_with_repair("task", _VALID_PLAN, call_model, "sys", "user")
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(calls, [])

    async def test_repairable_raw_recovered_without_model_call(self):
        damaged = "[{'description': 'x', 'role': 'worker', 'capabilities': ['tool_use']}]"
        calls = []

        async def call_model(system, user):
            calls.append(user)
            return "should never be called"

        plan = await plan_with_repair("task", damaged, call_model, "sys", "user")
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.steps[0].description, "x")
        self.assertEqual(calls, [])

    async def test_reask_recovers_when_second_response_is_valid(self):
        async def call_model(system, user):
            return _VALID_PLAN

        plan = await plan_with_repair("task", "not json at all", call_model, "sys", "user")
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(plan.steps[0].description, "do the thing")

    async def test_reask_prompt_includes_original_prompt_and_parse_error(self):
        captured = {}

        async def call_model(system, user):
            captured["system"] = system
            captured["user"] = user
            return _VALID_PLAN

        await plan_with_repair("task", "not json at all", call_model, "the-system", "the-original-user-prompt")
        self.assertEqual(captured["system"], "the-system")
        self.assertIn("the-original-user-prompt", captured["user"])
        self.assertIn("invalid JSON", captured["user"])

    async def test_returns_none_when_everything_fails(self):
        call_count = 0

        async def call_model(system, user):
            nonlocal call_count
            call_count += 1
            return "still not json"

        plan = await plan_with_repair("task", "not json at all", call_model, "sys", "user")
        self.assertIsNone(plan)
        self.assertEqual(call_count, 1)   # exactly one re-ask, never looped

    async def test_none_response_from_reask_handled_gracefully(self):
        async def call_model(system, user):
            return None

        plan = await plan_with_repair("task", "not json at all", call_model, "sys", "user")
        self.assertIsNone(plan)


if __name__ == "__main__":
    unittest.main()
