"""
Unit tests -- shared plan parsing (tasker/orchestrator/_parse.py)

Regression coverage for the bug where a single unrecognized capability
string inside an otherwise-valid model plan response caused parse_plan()
to silently discard the ENTIRE plan in favor of NanoOrchestrator's generic
fallback template, with no logging and no way for a caller to detect it.
"""
import json
import unittest

from tasker.orchestrator._parse import (
    CAPABILITY_ALIASES,
    build_plan_prompt,
    build_synthesize_prompt,
    parse_plan,
)
from tasker.orchestrator.tier1_single import SingleLLMOrchestrator
from tasker.workers.base import (
    Capability,
    ClassifierResult,
    ExecutionPlan,
    ModelUsage,
    TaskType,
    WorkerResult,
    WorkerStatus,
    WorkerToolResult,
)


def _result(output: str | None, tool_results: list | None = None) -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id="w1",
        status=WorkerStatus.SUCCESS,
        output=output,
        tool_results=tool_results or [],
        usage=ModelUsage(0, 0, 0.0),
        duration_ms=0,
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


class TestParsePlanNonObjectArrayElements(unittest.TestCase):
    """
    Live-observed on TASKER-P1: a plan array element that isn't itself a
    JSON object (e.g. a bare string) must return None (triggering the
    NanoOrchestrator fallback), not raise an uncaught AttributeError out
    of item.get()/item["description"].
    """

    def test_bare_string_array_element_returns_none(self):
        with self.assertLogs("tasker.orchestrator._parse", level="WARNING") as cm:
            plan = parse_plan("task", '["just a plain string", {"description": "ok"}]')
        self.assertIsNone(plan)
        self.assertIn("failed to parse", "\n".join(cm.output))

    def test_all_bare_strings_returns_none(self):
        plan = parse_plan("task", '["one", "two", "three"]')
        self.assertIsNone(plan)


class TestParsePlanDuplicateDescriptionKey(unittest.TestCase):
    """
    Live-observed (Designlab1, lfm2.5-thinking:latest): the model crammed
    a 4-intent "create, verify, read, confirm" task into 2 JSON objects,
    each repeating the "description" key twice. Plain json.loads() would
    silently keep only the LAST value, corrupting the step's real first
    intent with no error -- parse_plan() must instead split such an
    object into separate steps, recovering both descriptions.
    """

    def test_duplicate_description_key_splits_into_two_steps(self):
        # json.dumps() can't produce duplicate keys (dict keys are
        # unique) -- hand-crafted raw JSON, verbatim shape observed live.
        raw = (
            '[{"description": "Create the file", "role": "worker", '
            '"capabilities": ["tool_use"], "description": "Verify it exists"}]'
        )
        plan = parse_plan("create then verify a file", raw)
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].description, "Create the file")
        self.assertEqual(plan.steps[1].description, "Verify it exists")

    def test_split_steps_inherit_shared_role_and_capabilities(self):
        raw = (
            '[{"description": "Create the file", "role": "verifier", '
            '"capabilities": ["code"], "description": "Verify it exists"}]'
        )
        plan = parse_plan("create then verify a file", raw)
        self.assertEqual(plan.steps[0].role, plan.steps[1].role)
        self.assertIn(Capability.CODE, plan.steps[0].required_capabilities)
        self.assertIn(Capability.CODE, plan.steps[1].required_capabilities)

    def test_two_step_array_each_with_duplicate_key_yields_four_steps(self):
        # The exact shape observed live: 2 array elements, each internally
        # duplicated -- should recover all 4 originally-intended steps.
        raw = (
            '[{"description": "Create hello.txt", "role": "worker", '
            '"capabilities": ["tool_use"], "description": "Verify it exists"},'
            '{"description": "Read hello.txt", "role": "worker", '
            '"capabilities": ["tool_use"], "description": "Confirm contents"}]'
        )
        plan = parse_plan("create then read back a file", raw)
        self.assertEqual(len(plan.steps), 4)
        self.assertEqual(
            [s.description for s in plan.steps],
            ["Create hello.txt", "Verify it exists", "Read hello.txt", "Confirm contents"],
        )
        self.assertEqual([s.index for s in plan.steps], [0, 1, 2, 3])

    def test_no_duplicate_key_behaves_exactly_as_before(self):
        raw = json.dumps([
            {"description": "analyze", "role": "thinker", "capabilities": ["tool_use"]},
        ])
        plan = parse_plan("task", raw)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(plan.steps[0].description, "analyze")


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


class TestBuildSynthesizePrompt(unittest.TestCase):

    def test_no_output_no_tool_results_shows_placeholder(self):
        prompt = build_synthesize_prompt("task", [_result(None)])
        self.assertIn("Step 1: (no output)", prompt)

    def test_real_tool_output_included_even_when_prose_empty(self):
        """The exact case this closes: a step whose model prose was lost
        (e.g. inside a reasoning model's <think> block) should still
        surface real, already-executed tool output to the synthesizer."""
        tr = WorkerToolResult(
            tool_name="bash", tool_input={"command": "ls"},
            tool_output="file1.py\nfile2.py", error=None, duration_ms=5,
        )
        prompt = build_synthesize_prompt("task", [_result(None, [tr])])
        self.assertIn("Step 1: (no output)", prompt)
        self.assertIn("[tool: bash] -> file1.py\nfile2.py", prompt)

    def test_unexecuted_tool_results_omitted(self):
        """A tool_result with tool_output=None (never executed / errored)
        must not show up as fabricated grounding."""
        tr = WorkerToolResult(
            tool_name="bash", tool_input={"command": "ls"},
            tool_output=None, error="timed out", duration_ms=30000,
        )
        prompt = build_synthesize_prompt("task", [_result("some prose", [tr])])
        self.assertNotIn("[tool: bash]", prompt)


class TestResearchModeGroundingPrompts(unittest.TestCase):
    """
    SDD 5.1a: build_plan_prompt()/build_synthesize_prompt() append an
    explicit grounding requirement when mode_name == "research" -- fixing
    a live bug where a research task fabricated an entire model
    comparison and a benchmark statistic with zero tool calls, including
    invented factual content in the step description itself.
    """

    def test_plan_prompt_unaffected_by_default(self):
        prompt = build_plan_prompt("task", _classifier(), [])
        self.assertNotIn("GROUNDING", prompt)

    def test_plan_prompt_unaffected_for_other_modes(self):
        prompt = build_plan_prompt("task", _classifier(), [], mode_name="chat")
        self.assertNotIn("GROUNDING", prompt)

    def test_plan_prompt_gains_grounding_requirement_for_research(self):
        prompt = build_plan_prompt("task", _classifier(), [], mode_name="research")
        self.assertIn("GROUNDING REQUIREMENT", prompt)
        self.assertIn("web_search", prompt)

    def test_plan_prompt_grounding_forbids_factual_step_descriptions(self):
        prompt = build_plan_prompt("task", _classifier(), [], mode_name="research")
        self.assertIn("never assert factual claims", prompt)

    def test_plan_prompt_original_content_still_present_with_grounding(self):
        prompt = build_plan_prompt("my task", _classifier(), [], mode_name="research")
        self.assertIn("Task: my task", prompt)

    def test_synthesize_prompt_unaffected_by_default(self):
        prompt = build_synthesize_prompt("task", [_result("answer")])
        self.assertNotIn("GROUNDING", prompt)

    def test_synthesize_prompt_gains_citation_requirement_for_research(self):
        prompt = build_synthesize_prompt("task", [_result("answer")], mode_name="research")
        self.assertIn("GROUNDING REQUIREMENT", prompt)
        self.assertIn("cite", prompt.lower())

    def test_synthesize_prompt_original_content_still_present_with_grounding(self):
        prompt = build_synthesize_prompt("my task", [_result("answer")], mode_name="research")
        self.assertIn("Original task: my task", prompt)
        self.assertIn("answer", prompt)


if __name__ == "__main__":
    unittest.main()
