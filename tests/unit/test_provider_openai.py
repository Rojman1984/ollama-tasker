"""
Unit tests -- OpenAIProvider (tasker/workers/providers/openai_provider.py)
Phase 4 -- SDD Section 5.6.3
All HTTP is mocked via _post_fn / _get_fn injection.
"""
import json
import unittest

from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    LatencyClass,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    ToolDefinition,
    ToolProtocol,
    WorkerManifest,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.openai_provider import OpenAIProvider


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _manifest(model_id: str = "gpt-4o-mini") -> WorkerManifest:
    return WorkerManifest(
        id="openai-w1",
        provider=ProviderType.OPENAI,
        model_id=model_id,
        compute_location=ComputeLocation.DIRECT_CLOUD,
        capabilities={Capability.TOOL_USE, Capability.REASONING},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=128000,
        cost_input=0.15,
        cost_output=0.60,
        ollama_usage_level=None,
        latency_class=LatencyClass.FAST,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _task(instruction: str = "answer me") -> WorkerTask:
    return WorkerTask(
        task_id="t-003",
        step_index=0,
        role=AgentRole.WORKER,
        instruction=instruction,
        tools=[],
        context={},
        routing_policy=RoutingPolicy.SPEED_OPTIMIZED,
        privacy_tier=PrivacyTier.ANY_CLOUD,
    )


def _ok_response(content: str = "Hi!", tool_calls: list | None = None) -> dict:
    return {
        "id": "chatcmpl-001",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": tool_calls or None,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 80,
            "completion_tokens": 30,
            "total_tokens": 110,
        },
    }


def _make_post(status: int, response: dict):
    async def _post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
        return status, response
    return _post


def _make_get(status: int, response: dict):
    async def _get(url: str, headers: dict) -> tuple[int, dict]:
        return status, response
    return _get


def _provider(post_status=200, post_resp=None, get_status=200, get_resp=None):
    return OpenAIProvider(
        api_key="sk-test",
        _post_fn=_make_post(post_status, post_resp or _ok_response()),
        _get_fn=_make_get(get_status, get_resp or {"data": []}),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestOpenAIProviderSupports(unittest.TestCase):

    def test_supports_openai_provider(self):
        p = _provider()
        self.assertTrue(p.supports(_manifest()))

    def test_does_not_support_fugu(self):
        p = _provider()
        w = _manifest()
        w.provider = ProviderType.FUGU
        self.assertFalse(p.supports(w))


class TestOpenAIProviderHealthCheck(unittest.IsolatedAsyncioTestCase):

    async def test_health_check_true_when_model_listed(self):
        p = _provider(get_resp={"data": [{"id": "gpt-4o-mini"}]})
        self.assertTrue(await p.health_check(_manifest()))

    async def test_health_check_false_when_model_not_listed(self):
        p = _provider(get_resp={"data": [{"id": "gpt-4o"}]})
        self.assertFalse(await p.health_check(_manifest()))

    async def test_health_check_false_on_500(self):
        p = _provider(get_status=500, get_resp={})
        self.assertFalse(await p.health_check(_manifest()))


class TestOpenAIProviderExecute(unittest.IsolatedAsyncioTestCase):

    async def test_execute_success(self):
        p = _provider(post_resp=_ok_response("Hello from GPT!"))
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertEqual(result.output, "Hello from GPT!")

    async def test_execute_usage_tracked(self):
        p = _provider()
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.usage.input_tokens, 80)
        self.assertEqual(result.usage.output_tokens, 30)

    async def test_execute_cost_calculated(self):
        p = _provider()
        result = await p.execute(_task(), _manifest())
        expected = 80 * 0.15 / 1e6 + 30 * 0.60 / 1e6
        self.assertAlmostEqual(result.usage.cost_usd, expected, places=10)

    async def test_execute_tool_calls_extracted(self):
        native_calls = [{
            "id": "call_xyz",
            "type": "function",
            "function": {
                "name": "get_weather",
                "arguments": json.dumps({"location": "NYC"}),
            },
        }]
        p = _provider(post_resp=_ok_response(content=None, tool_calls=native_calls))
        result = await p.execute(_task(), _manifest())
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0].tool_name, "get_weather")
        self.assertEqual(result.tool_results[0].tool_input["location"], "NYC")

    async def test_execute_failed_on_non_200(self):
        p = _provider(post_status=401, post_resp={"error": {"message": "invalid key"}})
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.FAILED)
        self.assertIn("401", result.reason)

    async def test_execute_system_prompt_included(self):
        captured: list[dict] = []

        async def _recording_post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
            captured.append(payload)
            return 200, _ok_response()

        p = OpenAIProvider(api_key="k", _post_fn=_recording_post, _get_fn=_make_get(200, {}))
        task = _task()
        task.context["system_prompt"] = "Be concise."
        await p.execute(task, _manifest())
        messages = captured[0]["messages"]
        self.assertEqual(messages[0]["role"], "system")
        self.assertEqual(messages[0]["content"], "Be concise.")


if __name__ == "__main__":
    unittest.main()
