"""
Unit tests -- RESEARCH mode query-rewrite step (SDD 5.1a.5).

Covers `tasker/tools/query_rewrite.py` in isolation with mocked model
calls (no live network), and the wiring through `run_tool_loop()` with a
fake provider.
"""
from __future__ import annotations

import dataclasses
import unittest
from collections.abc import Awaitable, Callable
from pathlib import Path
from unittest import mock

from tasker.tools.loop import run_tool_loop
from tasker.tools.query_rewrite import build_query_rewriter, rewrite_search_query
from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    LatencyClass,
    ModelUsage,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
    WorkerToolResult,
)
from tasker.workers.providers.base import WorkerProviderBase


class TestRewriteSearchQuery(unittest.IsolatedAsyncioTestCase):

    async def test_returns_rewritten_query_from_model(self):
        async def call_model(system_prompt: str, user_prompt: str) -> str:
            return "latest python asyncio best practices"

        result = await rewrite_search_query(
            "Tell me about Python async patterns", "python async", call_model,
        )
        self.assertEqual(result, "latest python asyncio best practices")

    async def test_strips_surrounding_quotes(self):
        async def call_model(system_prompt: str, user_prompt: str) -> str:
            return '"python asyncio concurrency patterns"'

        result = await rewrite_search_query(
            "Tell me about Python async patterns", "python async", call_model,
        )
        self.assertEqual(result, "python asyncio concurrency patterns")

    async def test_falls_back_to_raw_query_on_empty_response(self):
        async def call_model(system_prompt: str, user_prompt: str) -> str:
            return ""

        result = await rewrite_search_query(
            "Tell me about Python async patterns", "python async", call_model,
        )
        self.assertEqual(result, "python async")

    async def test_falls_back_to_raw_query_on_exception(self):
        async def call_model(system_prompt: str, user_prompt: str) -> str:
            raise RuntimeError("model unavailable")

        result = await rewrite_search_query(
            "Tell me about Python async patterns", "python async", call_model,
        )
        self.assertEqual(result, "python async")

    async def test_falls_back_to_task_description_when_no_raw_query(self):
        async def call_model(system_prompt: str, user_prompt: str) -> str:
            return ""

        result = await rewrite_search_query(
            "Compare cheetah and greyhound top speed", None, call_model,
        )
        self.assertEqual(result, "Compare cheetah and greyhound top speed")

    async def test_prompt_mentions_task_and_draft_query(self):
        captured: dict[str, str] = {}

        async def call_model(system_prompt: str, user_prompt: str) -> str:
            captured["system"] = system_prompt
            captured["user"] = user_prompt
            return "rewritten"

        await rewrite_search_query(
            "Find the fastest land animal", "fastest animal", call_model,
        )
        self.assertIn("search-query specialist", captured["system"])
        self.assertIn("Find the fastest land animal", captured["user"])
        self.assertIn("fastest animal", captured["user"])

    async def test_prompt_omits_draft_query_section_when_empty(self):
        captured: dict[str, str] = {}

        async def call_model(system_prompt: str, user_prompt: str) -> str:
            captured["user"] = user_prompt
            return "rewritten"

        await rewrite_search_query("Find the fastest land animal", None, call_model)
        self.assertNotIn("Model's draft query", captured["user"])
        self.assertIn("Find the fastest land animal", captured["user"])


class _FakeProvider(WorkerProviderBase):
    """Provider that returns a fixed result, optionally with web_search calls."""

    def __init__(
        self,
        outputs: list[str],
        tool_results_per_turn: list[list[WorkerToolResult]] | None = None,
    ):
        self.outputs = outputs
        self.tool_results_per_turn = tool_results_per_turn or [[] for _ in outputs]
        self.calls: list[WorkerTask] = []

    def supports(self, worker):
        return True

    async def health_check(self, worker):
        return True

    async def execute(self, task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
        self.calls.append(task)
        idx = min(len(self.calls) - 1, len(self.outputs) - 1)
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=WorkerStatus.SUCCESS,
            output=self.outputs[idx],
            tool_results=list(self.tool_results_per_turn[idx]),
            usage=ModelUsage(0, 0, 0.0),
            duration_ms=0,
        )


def _worker() -> WorkerManifest:
    return WorkerManifest(
        id="w1",
        provider=ProviderType.OLLAMA,
        model_id="test:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=8192,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.FAST,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class TestBuildQueryRewriter(unittest.IsolatedAsyncioTestCase):

    async def test_rewriter_calls_provider_with_short_timeout(self):
        provider = _FakeProvider(outputs=["best python asyncio patterns"])
        rewriter = build_query_rewriter(provider, _worker())

        result = await rewriter("Tell me about Python async", "python async")

        self.assertEqual(result, "best python asyncio patterns")
        self.assertEqual(len(provider.calls), 1)
        task = provider.calls[0]
        self.assertEqual(task.timeout_s, 30.0)
        self.assertEqual(task.privacy_tier, PrivacyTier.LOCAL_ONLY)
        self.assertIn("Python async", task.instruction)
        self.assertIn("python async", task.instruction)

    async def test_cloud_worker_uses_ollama_cloud_ok_privacy_tier(self):
        cloud_worker = dataclasses.replace(_worker(), compute_location=ComputeLocation.OLLAMA_CLOUD)
        provider = _FakeProvider(outputs=["cloud query"])
        rewriter = build_query_rewriter(provider, cloud_worker)

        await rewriter("task", "draft")

        self.assertEqual(provider.calls[0].privacy_tier, PrivacyTier.OLLAMA_CLOUD_OK)


class TestRunToolLoopQueryRewrite(unittest.IsolatedAsyncioTestCase):

    def setUp(self):
        # Prevent real HTTP attempts from web_search/retrieve tool execution
        # in these loop-level wiring tests.
        self._search_patch = mock.patch(
            "tasker.tools.executor._search_get_fn",
            new=mock.AsyncMock(return_value=(200, {"web": {"results": []}})),
        )
        self._page_patch = mock.patch(
            "tasker.tools.executor._page_get_fn",
            new=mock.AsyncMock(return_value=(200, "")),
        )
        self._env_patch = mock.patch.dict(
            "os.environ", {"BRAVE_API_KEY": "test-key"}, clear=False,
        )
        self._search_patch.start()
        self._page_patch.start()
        self._env_patch.start()

    def tearDown(self):
        self._search_patch.stop()
        self._page_patch.stop()
        self._env_patch.stop()

    async def test_web_search_query_is_rewritten_before_execution(self):
        """The rewriter is applied to web_search tool inputs before they are
        executed, and the executed result carries the rewritten query."""
        provider = _FakeProvider(
            outputs=["", "done"],
            tool_results_per_turn=[
                [
                    WorkerToolResult(
                        tool_name="web_search",
                        tool_input={"query": "vague query"},
                        tool_output=None,
                        error=None,
                        duration_ms=0,
                    ),
                ],
                [],
            ],
        )

        async def rewriter(task_description: str, raw_query: str | None) -> str:
            return f"rewritten: {raw_query}"

        task = WorkerTask(
            task_id="t1",
            step_index=0,
            role=AgentRole.WORKER,
            instruction="Find current Python async patterns",
            tools=[],
            context={},
            routing_policy=RoutingPolicy.PRIVATE,
            privacy_tier=PrivacyTier.LOCAL_ONLY,
        )

        result = await run_tool_loop(
            task, _worker(), provider, cwd=Path.cwd(), query_rewriter=rewriter,
        )

        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0].tool_input["query"], "rewritten: vague query")

    async def test_non_web_search_tools_are_not_rewritten(self):
        provider = _FakeProvider(
            outputs=["", "done"],
            tool_results_per_turn=[
                [
                    WorkerToolResult(
                        tool_name="retrieve",
                        tool_input={"url": "https://example.com"},
                        tool_output=None,
                        error=None,
                        duration_ms=0,
                    ),
                ],
                [],
            ],
        )

        async def rewriter(task_description: str, raw_query: str | None) -> str:
            return "should not be used"

        task = WorkerTask(
            task_id="t1",
            step_index=0,
            role=AgentRole.WORKER,
            instruction="Get a page",
            tools=[],
            context={},
            routing_policy=RoutingPolicy.PRIVATE,
            privacy_tier=PrivacyTier.LOCAL_ONLY,
        )

        result = await run_tool_loop(
            task, _worker(), provider, cwd=Path.cwd(), query_rewriter=rewriter,
        )

        self.assertEqual(result.tool_results[0].tool_input["url"], "https://example.com")

    async def test_no_rewriter_leaves_web_search_query_unchanged(self):
        provider = _FakeProvider(
            outputs=["", "done"],
            tool_results_per_turn=[
                [
                    WorkerToolResult(
                        tool_name="web_search",
                        tool_input={"query": "original query"},
                        tool_output=None,
                        error=None,
                        duration_ms=0,
                    ),
                ],
                [],
            ],
        )

        task = WorkerTask(
            task_id="t1",
            step_index=0,
            role=AgentRole.WORKER,
            instruction="Find something",
            tools=[],
            context={},
            routing_policy=RoutingPolicy.PRIVATE,
            privacy_tier=PrivacyTier.LOCAL_ONLY,
        )

        result = await run_tool_loop(task, _worker(), provider, cwd=Path.cwd())

        self.assertEqual(result.tool_results[0].tool_input["query"], "original query")


if __name__ == "__main__":
    unittest.main()
