"""
Unit tests -- ReasoningOrchestrator Tier 3 (tasker/orchestrator/tier3_reasoning.py)
Phase 6 -- SDD Section 5.3
"""
import json
import unittest

from tasker.orchestrator.tier3_reasoning import ReasoningOrchestrator
from tasker.workers.base import (
    AgentRole,
    Capability,
    ClassifierResult,
    ExecutionPlan,
    ModelUsage,
    StepStatus,
    TaskType,
    WorkerResult,
    WorkerStatus,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _classifier(task_type: TaskType = TaskType.RESEARCH, complexity: float = 0.9) -> ClassifierResult:
    return ClassifierResult(
        task_type=task_type,
        complexity_score=complexity,
        required_capabilities={Capability.TOOL_USE, Capability.REASONING},
        suggested_workers=[],
        estimated_duration_s=120.0,
    )


def _result(output: str, worker_id: str = "w1") -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id=worker_id,
        status=WorkerStatus.SUCCESS,
        output=output,
        tool_results=[],
        usage=ModelUsage(input_tokens=200, output_tokens=400, cost_usd=0.0),
        duration_ms=2000,
    )


def _failed_result(reason: str = "timeout") -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id="w1",
        status=WorkerStatus.FAILED,
        output=None,
        tool_results=[],
        usage=ModelUsage(input_tokens=0, output_tokens=0, cost_usd=0.0),
        duration_ms=500,
        reason=reason,
    )


def _mock_call(response: str):
    async def _call(system: str, user: str) -> str:
        return response
    return _mock_call


def _mock_call(response: str):
    async def _call(system: str, user: str) -> str:
        return response
    return _call


def _make_orc(response: str) -> ReasoningOrchestrator:
    return ReasoningOrchestrator(model_id="qwen3:30b-a3b", call_model=_mock_call(response))


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestReasoningOrchestrator(unittest.IsolatedAsyncioTestCase):

    # ------------------------------------------------------------------ #
    # plan()
    # ------------------------------------------------------------------ #

    async def test_plan_parses_valid_json(self):
        plan_json = json.dumps([
            {"description": "gather sources", "role": "thinker", "capabilities": ["tool_use", "search"]},
            {"description": "synthesize findings", "role": "verifier", "capabilities": ["tool_use", "reasoning"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("research quantum computing", _classifier(), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 2)
        self.assertEqual(plan.steps[0].role, AgentRole.THINKER)
        self.assertEqual(plan.steps[1].role, AgentRole.VERIFIER)

    async def test_plan_falls_back_to_nano_on_bad_json(self):
        orc = _make_orc("I have thought deeply and...")  # not JSON
        plan = await orc.plan("task", _classifier(TaskType.RESEARCH), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertGreater(len(plan.steps), 0)

    async def test_plan_all_steps_pending(self):
        plan_json = json.dumps([
            {"description": "step one", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("task", _classifier(), [])
        self.assertEqual(plan.steps[0].status, StepStatus.PENDING)

    async def test_plan_injects_tool_use(self):
        plan_json = json.dumps([
            {"description": "reason deeply", "role": "thinker", "capabilities": ["reasoning"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("task", _classifier(), [])
        self.assertIn(Capability.TOOL_USE, plan.steps[0].required_capabilities)

    async def test_plan_preserves_original_task(self):
        plan_json = json.dumps([
            {"description": "do it", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = _make_orc(plan_json)
        plan = await orc.plan("my reasoning task", _classifier(), [])
        self.assertEqual(plan.original_task, "my reasoning task")

    # ------------------------------------------------------------------ #
    # synthesize()
    # ------------------------------------------------------------------ #

    async def test_synthesize_returns_model_output(self):
        orc = _make_orc("Here is the comprehensive synthesis.")
        output = await orc.synthesize("original task", [_result("finding A"), _result("finding B")])
        self.assertEqual(output, "Here is the comprehensive synthesis.")

    async def test_synthesize_passes_task_and_outputs(self):
        captured: list[str] = []

        async def _recording(system: str, user: str) -> str:
            captured.append(user)
            return "done"

        orc = ReasoningOrchestrator(model_id="qwen3:30b-a3b", call_model=_recording)
        await orc.synthesize("complex research task", [_result("data X"), _result("data Y")])
        self.assertTrue(any("complex research task" in u for u in captured))
        self.assertTrue(any("data X" in u for u in captured))

    # ------------------------------------------------------------------ #
    # should_retry()
    # ------------------------------------------------------------------ #

    async def test_should_retry_parses_true(self):
        retry_json = json.dumps({"should_retry": True, "reassign": True, "reason": "model overloaded"})
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        plan = await _make_orc(plan_json).plan("task", _classifier(), [])
        decision = await _make_orc(retry_json).should_retry(plan, _failed_result())
        self.assertTrue(decision.should_retry)
        self.assertTrue(decision.reassign)
        self.assertEqual(decision.reason, "model overloaded")

    async def test_should_retry_falls_back_on_malformed(self):
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        plan = await _make_orc(plan_json).plan("task", _classifier(), [])
        decision = await _make_orc("cannot decide").should_retry(plan, _failed_result())
        self.assertFalse(decision.should_retry)
        self.assertIn("ReasoningOrchestrator", decision.reason)

    # ------------------------------------------------------------------ #
    # Structural distinction from Tier 1
    # ------------------------------------------------------------------ #

    async def test_model_id_is_stored(self):
        orc = ReasoningOrchestrator(model_id="deepseek-r1:32b", call_model=_mock_call("[]"))
        self.assertEqual(orc._model_id, "deepseek-r1:32b")

    async def test_single_call_model_used_for_all_operations(self):
        """Verify a single call_model handles plan, synthesize, and retry."""
        calls: list[tuple[str, str]] = []

        async def _recording(system: str, user: str) -> str:
            calls.append((system, user))
            if "Task:" in user and "Available workers:" in user:
                return json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
            if "Original task:" in user:
                return "synthesized"
            return json.dumps({"should_retry": False, "reassign": False, "reason": "done"})

        orc = ReasoningOrchestrator(model_id="deepseek-r1:32b", call_model=_recording)
        plan = await orc.plan("task", _classifier(), [])
        await orc.synthesize("task", [_result("out")])
        await orc.should_retry(plan, _failed_result())
        self.assertEqual(len(calls), 3)   # one call per operation, all through same model


if __name__ == "__main__":
    unittest.main()
