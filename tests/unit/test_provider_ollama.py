"""
Unit tests -- OllamaProvider (tasker/workers/providers/ollama.py)
Phase 4 -- SDD Section 5.6.1
All HTTP is mocked via _post_fn / _get_fn injection.
"""
import json
import unittest

from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    LatencyClass,
    ModelUsage,
    OllamaQueueFullError,
    OllamaPlan,
    OllamaUsageLevel,
    ProviderType,
    RoutingPolicy,
    ToolDefinition,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.ollama import OllamaProvider


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _manifest(
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
    model_id: str = "lfm2.5:latest",
) -> WorkerManifest:
    return WorkerManifest(
        id="ollama-w1",
        provider=ProviderType.OLLAMA,
        model_id=model_id,
        compute_location=compute_location,
        capabilities={Capability.TOOL_USE, Capability.CODE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=(
            OllamaUsageLevel.MEDIUM
            if compute_location == ComputeLocation.OLLAMA_CLOUD else None
        ),
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _task(instruction: str = "say hello", tools: list | None = None) -> WorkerTask:
    return WorkerTask(
        task_id="t-001",
        step_index=0,
        role=AgentRole.WORKER,
        instruction=instruction,
        tools=tools or [],
        context={},
        routing_policy=RoutingPolicy.COST_OPTIMIZED,
        privacy_tier=__import__("tasker.workers.base", fromlist=["PrivacyTier"]).PrivacyTier.LOCAL_ONLY,
    )


def _ok_response(content: str = "Hello!", tool_calls: list | None = None) -> dict:
    return {
        "model": "lfm2.5:latest",
        "message": {
            "role": "assistant",
            "content": content,
            "tool_calls": tool_calls or [],
        },
        "prompt_eval_count": 50,
        "eval_count": 20,
        "done": True,
    }


def _make_post(status: int, response: dict, captured: list | None = None):
    async def _post(url: str, payload: dict) -> tuple[int, dict]:
        # strip the injected _timeout key so tests can inspect the payload cleanly
        payload.pop("_timeout", None)
        if captured is not None:
            captured.append(payload)
        return status, response
    return _post


def _make_get(status: int, response: dict):
    async def _get(url: str) -> tuple[int, dict]:
        return status, response
    return _get


def _provider(post_status=200, post_response=None, get_status=200, get_response=None,
              concurrency_mgr=None, captured_payloads: list | None = None) -> OllamaProvider:
    return OllamaProvider(
        base_url="http://localhost:11434",
        concurrency_mgr=concurrency_mgr,
        _post_fn=_make_post(post_status, post_response or _ok_response(), captured_payloads),
        _get_fn=_make_get(get_status, get_response or {"models": []}),
    )


def _lfm25_manifest(tool_result_role: str | None = "tool") -> WorkerManifest:
    m = _manifest(model_id="lfm2.5-thinking:latest")
    m.tool_protocol = ToolProtocol.LFM25
    m.tool_result_role = tool_result_role
    return m


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestOllamaProviderSupports(unittest.TestCase):

    def test_supports_ollama_provider(self):
        p = _provider()
        self.assertTrue(p.supports(_manifest()))

    def test_does_not_support_anthropic(self):
        p = _provider()
        w = _manifest()
        w.provider = ProviderType.ANTHROPIC
        self.assertFalse(p.supports(w))


class TestOllamaProviderHealthCheck(unittest.IsolatedAsyncioTestCase):

    async def test_health_check_true_when_model_listed(self):
        p = _provider(get_response={"models": [{"name": "lfm2.5:latest"}]})
        self.assertTrue(await p.health_check(_manifest()))

    async def test_health_check_false_when_model_not_listed(self):
        p = _provider(get_response={"models": [{"name": "other:latest"}]})
        self.assertFalse(await p.health_check(_manifest()))

    async def test_health_check_false_on_non_200(self):
        p = _provider(get_status=500, get_response={})
        self.assertFalse(await p.health_check(_manifest()))


class TestOllamaProviderExecuteLocal(unittest.IsolatedAsyncioTestCase):

    async def test_execute_success_returns_success_result(self):
        p = _provider(post_response=_ok_response("Hello!"))
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertEqual(result.output, "Hello!")
        self.assertEqual(result.task_id, "t-001")
        self.assertEqual(result.worker_id, "ollama-w1")

    async def test_execute_builds_usage(self):
        p = _provider(post_response=_ok_response())
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.usage.input_tokens, 50)
        self.assertEqual(result.usage.output_tokens, 20)

    async def test_execute_fails_on_non_200(self):
        p = _provider(post_status=503, post_response={"error": "service unavailable"})
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.FAILED)
        self.assertIn("503", result.reason)

    async def test_execute_raises_on_429(self):
        p = _provider(post_status=429, post_response={"error": "queue full"})
        with self.assertRaises(OllamaQueueFullError):
            await p.execute(_task(), _manifest(ComputeLocation.LOCAL_HARDWARE))

    async def test_execute_tool_calls_normalized(self):
        resp = _ok_response(
            content="",
            tool_calls=[{"function": {"name": "bash", "arguments": {"cmd": "ls"}}}],
        )
        p = _provider(post_response=resp)
        result = await p.execute(_task(), _manifest())
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0].tool_name, "bash")
        self.assertEqual(result.tool_results[0].tool_input["cmd"], "ls")


class TestOllamaProviderProtocolRouting(unittest.IsolatedAsyncioTestCase):
    """Phase 7.5: LFM25 protocol routing -- see SDD_ADDENDUM_7.5.md A.2b."""

    def _tools(self) -> list[ToolDefinition]:
        return [ToolDefinition(
            name="get_weather",
            description="Get current weather",
            parameters={"type": "object", "properties": {"location": {"type": "string"}}},
        )]

    async def test_native_protocol_includes_tools_in_payload(self):
        captured: list = []
        p = _provider(post_response=_ok_response(), captured_payloads=captured)
        await p.execute(_task(tools=self._tools()), _manifest())
        self.assertIn("tools", captured[0])
        self.assertEqual(captured[0]["tools"][0]["function"]["name"], "get_weather")

    async def test_lfm25_protocol_excludes_tools_from_payload(self):
        captured: list = []
        p = _provider(post_response=_ok_response(), captured_payloads=captured)
        await p.execute(_task(tools=self._tools()), _lfm25_manifest())
        self.assertNotIn("tools", captured[0])

    async def test_lfm25_protocol_injects_list_of_tools_into_system_message(self):
        captured: list = []
        p = _provider(post_response=_ok_response(), captured_payloads=captured)
        await p.execute(_task(tools=self._tools()), _lfm25_manifest())
        system_msgs = [m for m in captured[0]["messages"] if m["role"] == "system"]
        self.assertEqual(len(system_msgs), 1)
        self.assertIn("List of tools:", system_msgs[0]["content"])
        self.assertIn("get_weather", system_msgs[0]["content"])

    async def test_lfm25_protocol_response_routed_through_extract_tool_calls(self):
        resp = _ok_response(content='[{"name": "get_weather", "arguments": {"location": "Austin"}}]')
        p = _provider(post_response=resp)
        result = await p.execute(_task(tools=self._tools()), _lfm25_manifest())
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0].tool_name, "get_weather")
        self.assertEqual(result.tool_results[0].tool_input, {"location": "Austin"})

    async def test_lfm25_protocol_pythonic_fallback_routed_correctly(self):
        resp = _ok_response(
            content='<|tool_call_start|>[get_weather(location="Austin")]<|tool_call_end|>'
        )
        p = _provider(post_response=resp)
        result = await p.execute(_task(tools=self._tools()), _lfm25_manifest())
        self.assertEqual(result.tool_results[0].tool_name, "get_weather")

    async def test_lfm25_protocol_no_tools_no_injection(self):
        captured: list = []
        p = _provider(post_response=_ok_response(), captured_payloads=captured)
        await p.execute(_task(tools=None), _lfm25_manifest())
        system_msgs = [m for m in captured[0]["messages"] if m["role"] == "system"]
        self.assertEqual(system_msgs, [])
        self.assertNotIn("tools", captured[0])


class TestOllamaProviderCloud(unittest.IsolatedAsyncioTestCase):

    async def test_cloud_deferred_when_no_slot(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        # Fill the one slot
        await mgr.try_acquire()
        p = _provider(concurrency_mgr=mgr)
        result = await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        self.assertEqual(result.status, WorkerStatus.DEFERRED)

    async def test_cloud_acquires_and_releases_slot(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        p = _provider(concurrency_mgr=mgr, post_response=_ok_response())
        self.assertEqual(mgr.slots_available, 1)
        await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        # Slot must be released after execute completes
        self.assertEqual(mgr.slots_available, 1)

    async def test_cloud_releases_slot_on_error(self):
        mgr = OllamaCloudConcurrencyManager(OllamaPlan.FREE)
        p = _provider(concurrency_mgr=mgr, post_status=500, post_response={})
        await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        self.assertEqual(mgr.slots_available, 1)

    async def test_no_concurrency_mgr_cloud_still_executes(self):
        """Cloud worker without a concurrency manager proceeds without slot check."""
        p = _provider(post_response=_ok_response("cloud response"))
        result = await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        self.assertEqual(result.status, WorkerStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
