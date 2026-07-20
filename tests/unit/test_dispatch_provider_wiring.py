"""
Unit tests -- _run_task()/_resume_task() provider-availability wiring
(tasker/runtime/dispatch.py).

Live bug (tasker-cli shell, chat mode): WorkerSelector picked fugu-ultra
even though provider_map only wires OllamaProvider -- the step then failed
mid-dispatch with "No provider for fugu" and the whole run ended in
"No results to synthesize." Fix: registry.apply_provider_availability()
excludes workers with no wired provider *before* planning/selection.
These tests drive the real _run_task()/_resume_task() functions with a
fake orchestrator + fake provider, never touching HTTP.
"""
import dataclasses
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tasker.modes.base import ModeConfigurator
from tasker.runtime.dispatch import _run_task, _resume_task
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import Checkpoint, CheckpointStore
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
)
from tasker.workers.providers.base import WorkerProviderBase
from tasker.workers.registry import WorkerRegistry


def _worker(worker_id: str, provider: ProviderType, capability_score: float) -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=provider,
        model_id="test:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
        capability_scores={"tool_use": capability_score},
    )


def _plan() -> ExecutionPlan:
    return ExecutionPlan(
        plan_id="p1",
        original_task="test task",
        steps=[
            PlanStep(
                index=0,
                description="step 0",
                role=AgentRole.WORKER,
                required_capabilities={Capability.TOOL_USE},
                depends_on=[],
                status=StepStatus.PENDING,
            )
        ],
        dependency_graph={},
    )


class _FakeProvider(WorkerProviderBase):
    def __init__(self) -> None:
        self.calls = 0

    def supports(self, worker):
        return True

    async def health_check(self, worker):
        return True

    async def execute(self, task, worker):
        self.calls += 1
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=WorkerStatus.SUCCESS,
            output="ok",
            tool_results=[],
            usage=ModelUsage(10, 10, 0.0),
            duration_ms=5,
        )


class _FakeOrchestrator:
    def __init__(self):
        self.synthesized = None

    async def plan(self, task, classifier_output, workers):
        return _plan()

    async def synthesize(self, task, results):
        self.synthesized = results
        return "synthesized output"


def _build_test_pipeline(provider, config):
    budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
    tmp = tempfile.TemporaryDirectory()
    store = CheckpointStore(Path(tmp.name))
    session_mgr = SessionManager(budget, store, LogNotifier(), auto_resume=False)
    concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
    provider_map = {ProviderType.OLLAMA: provider}
    orchestrator = _FakeOrchestrator()
    pipeline = (
        "tier1_tasker", config, budget, session_mgr, concurrency_mgr,
        provider_map, orchestrator,
    )
    return pipeline, tmp, store


class TestRunTaskExcludesUnwiredProviderWorkers(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        base_config = ModeConfigurator().build("tier1_tasker", "chat")
        # CAPABILITY_FIRST so the higher-capability-score fugu worker would
        # win selection if it were ever a candidate -- proves exclusion
        # happens up front, not that it merely lost on ranking.
        mode = dataclasses.replace(base_config.mode, routing_policy=RoutingPolicy.CAPABILITY_FIRST)
        self.config = dataclasses.replace(base_config, mode=mode)

    async def test_fugu_worker_never_selected_when_only_ollama_wired(self):
        registry = WorkerRegistry()
        # fugu ranks strictly higher on CAPABILITY_FIRST -- would win
        # selection if it were ever considered a candidate.
        registry.register(_worker("fugu-w1", ProviderType.FUGU, capability_score=10.0))
        registry.register(_worker("ollama-w1", ProviderType.OLLAMA, capability_score=1.0))

        provider = _FakeProvider()
        pipeline, tmp, store = _build_test_pipeline(provider, self.config)
        try:
            with mock.patch(
                "tasker.runtime.dispatch._build_pipeline", return_value=pipeline
            ):
                await _run_task(
                    "do something", "chat", registry, store,
                    policy_override=RoutingPolicy.CAPABILITY_FIRST,
                )
        finally:
            tmp.cleanup()

        # fugu-ultra marked unavailable (no wired provider), never dropped
        self.assertFalse(registry.get("fugu-w1").available)
        self.assertIn("fugu-w1", {m.id for m in registry.list_all()})
        # the ollama worker executed successfully instead of the run
        # failing with "No results to synthesize."
        self.assertEqual(provider.calls, 1)
        self.assertEqual(registry.get("ollama-w1").id, "ollama-w1")

    async def test_resume_task_also_excludes_unwired_provider_workers(self):
        registry = WorkerRegistry()
        registry.register(_worker("fugu-w1", ProviderType.FUGU, capability_score=10.0))
        registry.register(_worker("ollama-w1", ProviderType.OLLAMA, capability_score=1.0))

        provider = _FakeProvider()
        pipeline, tmp, store = _build_test_pipeline(provider, self.config)
        try:
            budget = pipeline[2]
            cp = Checkpoint.new(
                mode="chat",
                hardware_profile="tier1_tasker",
                original_task="test task",
                budget_snapshot=budget.snapshot(),
                plan=_plan(),
                completed_steps=[],
                current_step_index=0,
                resume_at=datetime.now().astimezone(),
                auto_resume=False,
            )
            store.save(cp)
            with mock.patch(
                "tasker.runtime.dispatch._build_pipeline", return_value=pipeline
            ):
                await _resume_task(
                    cp.id, registry, store,
                    policy_override=RoutingPolicy.CAPABILITY_FIRST,
                )
        finally:
            tmp.cleanup()

        self.assertFalse(registry.get("fugu-w1").available)
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
