"""
Unit tests -- CHAT mode direct dispatch (SDD 5.3a, tasker/runtime/dispatch.py).

Live bug: a "Hello" in chat mode was routed through the full orchestrator
pipeline (plan -> execute-steps -> synthesize). The worker received the
PLANNER'S generated step description ("Processing available workers...")
instead of the user's actual message -- a pure hallucination artifact --
and three sequential LLM calls took ~56s to first response. Fix:
_run_chat_task() calls the chat worker directly, once, with the raw
message and running conversation history, never touching plan()/
synthesize(). These tests drive it with a fake orchestrator + fake
provider, never touching HTTP.
"""
import dataclasses
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from tasker.modes.base import ModeConfigurator
from tasker.runtime.dispatch import (
    DEFAULT_CHAT_WORKER_ID,
    _run_chat_task,
    _select_chat_worker,
)
from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import CheckpointStore
from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.session.manager import SessionManager
from tasker.session.notifier import LogNotifier
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ModelUsage,
    OllamaPlan,
    ProviderType,
    RoutingPolicy,
    TaskerPolicyError,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
)
from tasker.workers.providers.base import WorkerProviderBase
from tasker.workers.registry import WorkerRegistry


def _worker(
    worker_id: str,
    capability_score: float = 1.0,
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
    latency_class: LatencyClass = LatencyClass.MEDIUM,
) -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="test:latest",
        compute_location=compute_location,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=latency_class,
        available=True,
        requires_gpu=False,
        vram_mb=None,
        capability_scores={"tool_use": capability_score},
    )


class _RecordingProvider(WorkerProviderBase):
    """Echoes back the exact instruction/history it received, so tests can
    assert the worker got the user's raw message, not a planner artifact."""

    def __init__(self, reply: str = "Hi there!") -> None:
        self.calls = 0
        self.reply = reply
        self.last_instruction: str | None = None
        self.last_messages: list[dict] | None = None

    def supports(self, worker):
        return True

    async def health_check(self, worker):
        return True

    async def execute(self, task, worker):
        self.calls += 1
        self.last_instruction = task.instruction
        self.last_messages = task.context.get("messages")
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=WorkerStatus.SUCCESS,
            output=self.reply,
            tool_results=[],
            usage=ModelUsage(10, 10, 0.0),
            duration_ms=5,
        )


def _pipeline(provider, effort_policy_worker_pool=None):
    config = ModeConfigurator().build("tier1_tasker", "chat")
    budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
    tmp = tempfile.TemporaryDirectory()
    store = CheckpointStore(Path(tmp.name))
    session_mgr = SessionManager(budget, store, LogNotifier(), auto_resume=False)
    concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)
    provider_map = {ProviderType.OLLAMA: provider}
    pipeline = ("tier1_tasker", config, budget, session_mgr, concurrency_mgr, provider_map, None)
    return pipeline, tmp, store, config, concurrency_mgr


class TestSelectChatWorker(unittest.TestCase):

    def setUp(self):
        self.registry = WorkerRegistry()
        self.config = ModeConfigurator().build("tier1_tasker", "chat")
        self.concurrency_mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)

    def test_defaults_to_always_loaded_local_worker_at_med_effort(self):
        self.registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        self.registry.register(_worker("some-other-worker", capability_score=99.0))
        worker = _select_chat_worker(self.registry, self.config, self.concurrency_mgr, None, "med")
        self.assertEqual(worker.id, DEFAULT_CHAT_WORKER_ID)

    def test_explicit_model_override_always_wins(self):
        self.registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        self.registry.register(_worker("claude-sonnet-4-6"))
        worker = _select_chat_worker(
            self.registry, self.config, self.concurrency_mgr, "claude-sonnet-4-6", "med"
        )
        self.assertEqual(worker.id, "claude-sonnet-4-6")

    def test_model_override_unknown_id_raises(self):
        self.registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        with self.assertRaises(TaskerPolicyError):
            _select_chat_worker(self.registry, self.config, self.concurrency_mgr, "nope", "med")

    def test_model_override_unavailable_worker_raises(self):
        w = _worker(DEFAULT_CHAT_WORKER_ID)
        w.available = False
        self.registry.register(w)
        with self.assertRaises(TaskerPolicyError):
            _select_chat_worker(
                self.registry, self.config, self.concurrency_mgr, DEFAULT_CHAT_WORKER_ID, "med"
            )

    def test_high_effort_without_model_override_selects_by_capability(self):
        self.registry.register(_worker(DEFAULT_CHAT_WORKER_ID, capability_score=1.0))
        self.registry.register(_worker("stronger-worker", capability_score=99.0))
        worker = _select_chat_worker(self.registry, self.config, self.concurrency_mgr, None, "high")
        self.assertEqual(worker.id, "stronger-worker")

    def test_low_effort_without_model_override_selects_by_speed(self):
        self.registry.register(_worker(DEFAULT_CHAT_WORKER_ID, latency_class=LatencyClass.SLOW))
        self.registry.register(_worker("fast-worker", latency_class=LatencyClass.FAST))
        worker = _select_chat_worker(self.registry, self.config, self.concurrency_mgr, None, "low")
        self.assertEqual(worker.id, "fast-worker")

    def test_default_worker_missing_from_registry_falls_back_to_selector(self):
        self.registry.register(_worker("only-worker"))
        worker = _select_chat_worker(self.registry, self.config, self.concurrency_mgr, None, "med")
        self.assertEqual(worker.id, "only-worker")


class TestRunChatTask(unittest.IsolatedAsyncioTestCase):

    async def test_worker_receives_raw_user_message_not_a_planner_artifact(self):
        registry = WorkerRegistry()
        registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        provider = _RecordingProvider(reply="Hi! How can I help?")
        pipeline, tmp, store, config, concurrency_mgr = _pipeline(provider)
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                history: list[dict] = []
                await _run_chat_task("Hello", registry, store, history)
        finally:
            tmp.cleanup()

        self.assertEqual(provider.last_instruction, "Hello")
        self.assertEqual(provider.calls, 1)   # exactly one call -- no plan/synthesize

    async def test_no_orchestrator_calls_made(self):
        # pipeline's orchestrator slot is None -- if _run_chat_task ever
        # called .plan()/.synthesize() on it, this would raise AttributeError.
        registry = WorkerRegistry()
        registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        provider = _RecordingProvider()
        pipeline, tmp, store, config, concurrency_mgr = _pipeline(provider)
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                await _run_chat_task("Hello", registry, store, [])
        finally:
            tmp.cleanup()   # no exception means orchestrator (None) was never touched

    async def test_history_accumulates_across_turns(self):
        registry = WorkerRegistry()
        registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        provider = _RecordingProvider(reply="second reply")
        pipeline, tmp, store, config, concurrency_mgr = _pipeline(provider)
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                history: list[dict] = []
                await _run_chat_task("first message", registry, store, history)
                await _run_chat_task("second message", registry, store, history)
        finally:
            tmp.cleanup()

        self.assertEqual(len(history), 4)
        self.assertEqual(history[0], {"role": "user", "content": "first message"})
        self.assertEqual(history[1]["role"], "assistant")
        self.assertEqual(history[2], {"role": "user", "content": "second message"})
        # the second call's provider.execute() must have seen the full
        # prior history, not just the new message.
        self.assertEqual(len(provider.last_messages), 3)

    async def test_failed_result_does_not_poison_history(self):
        class _FailingProvider(WorkerProviderBase):
            def supports(self, worker):
                return True

            async def health_check(self, worker):
                return True

            async def execute(self, task, worker):
                return WorkerResult(
                    task_id=task.task_id, worker_id=worker.id,
                    status=WorkerStatus.FAILED, output=None, tool_results=[],
                    usage=ModelUsage(0, 0, 0.0), duration_ms=0, reason="boom",
                )

        registry = WorkerRegistry()
        registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        pipeline, tmp, store, config, concurrency_mgr = _pipeline(_FailingProvider())
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                history: list[dict] = []
                await _run_chat_task("Hello", registry, store, history)
        finally:
            tmp.cleanup()

        self.assertEqual(history, [])

    async def test_model_override_routes_to_the_pinned_worker(self):
        registry = WorkerRegistry()
        registry.register(_worker(DEFAULT_CHAT_WORKER_ID))
        registry.register(_worker("pinned-worker"))
        provider = _RecordingProvider()
        pipeline, tmp, store, config, concurrency_mgr = _pipeline(provider)
        try:
            with mock.patch("tasker.runtime.dispatch._build_pipeline", return_value=pipeline):
                await _run_chat_task(
                    "Hello", registry, store, [], model_override="pinned-worker"
                )
        finally:
            tmp.cleanup()
        self.assertEqual(provider.calls, 1)


if __name__ == "__main__":
    unittest.main()
