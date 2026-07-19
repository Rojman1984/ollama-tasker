"""
Unit tests -- CloudOrchestrator Tier 4 (tasker/orchestrator/tier4_cloud.py)
Phase 6 -- SDD Section 5.3
"""
import json
import unittest

from tasker.orchestrator.tier4_cloud import CloudOrchestrator
from tasker.workers.base import (
    AgentRole,
    Capability,
    ClassifierResult,
    ComputeLocation,
    ExecutionPlan,
    LatencyClass,
    ModelUsage,
    OllamaUsageLevel,
    PrivacyTier,
    ProviderType,
    StepStatus,
    TaskerPolicyError,
    TaskType,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase


# ------------------------------------------------------------------ #
# Fake provider
# ------------------------------------------------------------------ #

class _FakeProvider(WorkerProviderBase):
    """Configurable fake: returns a preset WorkerResult for any execute() call."""

    def __init__(self, output: str | None = None, status: WorkerStatus = WorkerStatus.SUCCESS) -> None:
        self._output = output
        self._status = status
        self.calls: list[WorkerTask] = []

    async def execute(self, task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
        self.calls.append(task)
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=self._status,
            output=self._output,
            tool_results=[],
            usage=ModelUsage(input_tokens=100, output_tokens=200, cost_usd=0.01),
            duration_ms=300,
        )

    async def health_check(self, worker: WorkerManifest) -> bool:
        return True

    def supports(self, worker: WorkerManifest) -> bool:
        return True


def _cloud_worker() -> WorkerManifest:
    return WorkerManifest(
        id="fugu-orchestrator",
        provider=ProviderType.ANTHROPIC,
        model_id="claude-3-5-sonnet",
        compute_location=ComputeLocation.DIRECT_CLOUD,
        capabilities={Capability.TOOL_USE, Capability.REASONING, Capability.LONG_CONTEXT},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=200_000,
        cost_input=3.0,
        cost_output=15.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _classifier(task_type: TaskType = TaskType.CODING, complexity: float = 0.8) -> ClassifierResult:
    return ClassifierResult(
        task_type=task_type,
        complexity_score=complexity,
        required_capabilities={Capability.TOOL_USE},
        suggested_workers=[],
        estimated_duration_s=60.0,
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


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestCloudOrchestrator(unittest.IsolatedAsyncioTestCase):

    # ------------------------------------------------------------------ #
    # Constructor guard
    # ------------------------------------------------------------------ #

    def test_local_only_raises_at_construction(self):
        with self.assertRaises(TaskerPolicyError):
            CloudOrchestrator(
                provider=_FakeProvider(),
                worker=_cloud_worker(),
                privacy_tier=PrivacyTier.LOCAL_ONLY,
            )

    def test_any_cloud_accepted(self):
        orc = CloudOrchestrator(
            provider=_FakeProvider(output="[]"),
            worker=_cloud_worker(),
            privacy_tier=PrivacyTier.ANY_CLOUD,
        )
        self.assertIsNotNone(orc)

    def test_ollama_cloud_ok_accepted(self):
        orc = CloudOrchestrator(
            provider=_FakeProvider(output="[]"),
            worker=_cloud_worker(),
            privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
        )
        self.assertIsNotNone(orc)

    # ------------------------------------------------------------------ #
    # plan() routes through provider
    # ------------------------------------------------------------------ #

    async def test_plan_parses_valid_json_from_provider(self):
        plan_json = json.dumps([
            {"description": "cloud step", "role": "worker", "capabilities": ["tool_use", "reasoning"]},
        ])
        provider = _FakeProvider(output=plan_json)
        orc = CloudOrchestrator(provider=provider, worker=_cloud_worker())
        plan = await orc.plan("cloud task", _classifier(), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertEqual(len(plan.steps), 1)
        self.assertEqual(len(provider.calls), 1)   # exactly one provider call made

    async def test_plan_falls_back_to_nano_on_provider_failure(self):
        provider = _FakeProvider(output=None, status=WorkerStatus.FAILED)
        orc = CloudOrchestrator(provider=provider, worker=_cloud_worker())
        plan = await orc.plan("task", _classifier(TaskType.CODING), [])
        # NanoOrchestrator fallback
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertGreater(len(plan.steps), 0)

    async def test_plan_falls_back_to_nano_on_bad_json(self):
        provider = _FakeProvider(output="this is prose, not JSON")
        orc = CloudOrchestrator(provider=provider, worker=_cloud_worker())
        plan = await orc.plan("task", _classifier(TaskType.RESEARCH), [])
        self.assertIsInstance(plan, ExecutionPlan)
        self.assertGreater(len(plan.steps), 0)

    async def test_plan_fallback_sets_used_fallback_flag(self):
        # Regression (Phase 8.1): tier 4 fell back without marking the plan.
        provider = _FakeProvider(output="this is prose, not JSON")
        orc = CloudOrchestrator(provider=provider, worker=_cloud_worker())
        plan = await orc.plan("task", _classifier(TaskType.RESEARCH), [])
        self.assertTrue(plan.used_fallback)

    async def test_plan_preserves_original_task(self):
        plan_json = json.dumps([
            {"description": "do it", "role": "worker", "capabilities": ["tool_use"]},
        ])
        orc = CloudOrchestrator(provider=_FakeProvider(output=plan_json), worker=_cloud_worker())
        plan = await orc.plan("my cloud task", _classifier(), [])
        self.assertEqual(plan.original_task, "my cloud task")

    # ------------------------------------------------------------------ #
    # synthesize() routes through provider
    # ------------------------------------------------------------------ #

    async def test_synthesize_returns_provider_output(self):
        orc = CloudOrchestrator(
            provider=_FakeProvider(output="Here is the cloud synthesis."),
            worker=_cloud_worker(),
        )
        output = await orc.synthesize("build a thing", [_result("step A"), _result("step B")])
        self.assertEqual(output, "Here is the cloud synthesis.")

    async def test_synthesize_fallback_on_provider_failure(self):
        orc = CloudOrchestrator(
            provider=_FakeProvider(output=None, status=WorkerStatus.FAILED),
            worker=_cloud_worker(),
        )
        output = await orc.synthesize("task", [_result("out")])
        self.assertIn("unavailable", output)

    async def test_synthesize_makes_one_provider_call(self):
        provider = _FakeProvider(output="done")
        orc = CloudOrchestrator(provider=provider, worker=_cloud_worker())
        await orc.synthesize("task", [_result("A")])
        self.assertEqual(len(provider.calls), 1)

    # ------------------------------------------------------------------ #
    # should_retry() routes through provider
    # ------------------------------------------------------------------ #

    async def test_should_retry_parses_true(self):
        retry_json = json.dumps({"should_retry": True, "reassign": False, "reason": "transient cloud error"})
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])

        plan_orc = CloudOrchestrator(provider=_FakeProvider(output=plan_json), worker=_cloud_worker())
        plan = await plan_orc.plan("task", _classifier(), [])

        retry_orc = CloudOrchestrator(provider=_FakeProvider(output=retry_json), worker=_cloud_worker())
        decision = await retry_orc.should_retry(plan, _failed_result())
        self.assertTrue(decision.should_retry)
        self.assertEqual(decision.reason, "transient cloud error")

    async def test_should_retry_falls_back_on_failure(self):
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        plan = await CloudOrchestrator(
            provider=_FakeProvider(output=plan_json), worker=_cloud_worker()
        ).plan("task", _classifier(), [])

        orc = CloudOrchestrator(
            provider=_FakeProvider(output=None, status=WorkerStatus.FAILED),
            worker=_cloud_worker(),
        )
        decision = await orc.should_retry(plan, _failed_result())
        self.assertFalse(decision.should_retry)
        self.assertIn("CloudOrchestrator", decision.reason)

    # ------------------------------------------------------------------ #
    # WorkerTask construction
    # ------------------------------------------------------------------ #

    async def test_worker_task_has_correct_privacy_tier(self):
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        provider = _FakeProvider(output=plan_json)
        orc = CloudOrchestrator(
            provider=provider,
            worker=_cloud_worker(),
            privacy_tier=PrivacyTier.OLLAMA_CLOUD_OK,
        )
        await orc.plan("task", _classifier(), [])
        self.assertEqual(provider.calls[0].privacy_tier, PrivacyTier.OLLAMA_CLOUD_OK)

    async def test_worker_task_role_is_thinker(self):
        plan_json = json.dumps([{"description": "s", "role": "worker", "capabilities": ["tool_use"]}])
        provider = _FakeProvider(output=plan_json)
        orc = CloudOrchestrator(provider=provider, worker=_cloud_worker())
        await orc.plan("task", _classifier(), [])
        self.assertEqual(provider.calls[0].role, AgentRole.THINKER)


if __name__ == "__main__":
    unittest.main()
