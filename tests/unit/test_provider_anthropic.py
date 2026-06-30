"""
Unit tests -- AnthropicProvider (tasker/workers/providers/anthropic.py)
Phase 4 -- SDD Section 5.6.2
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
from tasker.workers.providers.anthropic import AnthropicProvider


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _manifest(model_id: str = "claude-haiku-4-5-20251001") -> WorkerManifest:
    return WorkerManifest(
        id="anthropic-w1",
        provider=ProviderType.ANTHROPIC,
        model_id=model_id,
        compute_location=ComputeLocation.DIRECT_CLOUD,
        capabilities={Capability.TOOL_USE, Capability.REASONING},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=200000,
        cost_input=0.80,
        cost_output=4.00,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _task(instruction: str = "help me") -> WorkerTask:
    return WorkerTask(
        task_id="t-002",
        step_index=0,
        role=AgentRole.WORKER,
        instruction=instruction,
        tools=[],
        context={"system_prompt": "You are a helpful assistant."},
        routing_policy=RoutingPolicy.CAPABILITY_FIRST,
        privacy_tier=PrivacyTier.ANY_CLOUD,
    )


def _ok_response(text: str = "Sure!", tool_name: str | None = None) -> dict:
    content: list[dict] = [{"type": "text", "text": text}]
    if tool_name:
        content.append({
            "type": "tool_use",
            "id": "toolu_001",
            "name": tool_name,
            "input": {"param": "value"},
        })
    return {
        "id": "msg_001",
        "model": "claude-haiku-4-5-20251001",
        "content": content,
        "usage": {"input_tokens": 100, "output_tokens": 50},
        "stop_reason": "end_turn",
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
    return AnthropicProvider(
        api_key="test-key",
        _post_fn=_make_post(post_status, post_resp or _ok_response()),
        _get_fn=_make_get(get_status, get_resp or {"data": []}),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestAnthropicProviderSupports(unittest.TestCase):

    def test_supports_anthropic_provider(self):
        p = _provider()
        self.assertTrue(p.supports(_manifest()))

    def test_does_not_support_ollama(self):
        p = _provider()
        w = _manifest()
        w.provider = ProviderType.OLLAMA
        self.assertFalse(p.supports(w))


class TestAnthropicProviderHealthCheck(unittest.IsolatedAsyncioTestCase):

    async def test_health_check_true_when_model_listed(self):
        p = _provider(get_resp={"data": [{"id": "claude-haiku-4-5-20251001"}]})
        self.assertTrue(await p.health_check(_manifest()))

    async def test_health_check_false_when_model_not_listed(self):
        p = _provider(get_resp={"data": [{"id": "claude-opus-4-7"}]})
        self.assertFalse(await p.health_check(_manifest()))

    async def test_health_check_true_on_401_reachable(self):
        p = _provider(get_status=401, get_resp={"error": "auth"})
        self.assertTrue(await p.health_check(_manifest()))


class TestAnthropicProviderExecute(unittest.IsolatedAsyncioTestCase):

    async def test_execute_success(self):
        p = _provider(post_resp=_ok_response("Hello from Claude!"))
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertEqual(result.output, "Hello from Claude!")

    async def test_execute_usage_tracked(self):
        p = _provider()
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.usage.input_tokens, 100)
        self.assertEqual(result.usage.output_tokens, 50)

    async def test_execute_cost_calculated(self):
        p = _provider()
        result = await p.execute(_task(), _manifest())
        # 100 input @ $0.80/M + 50 output @ $4.00/M
        expected = 100 * 0.80 / 1e6 + 50 * 4.00 / 1e6
        self.assertAlmostEqual(result.usage.cost_usd, expected, places=10)

    async def test_execute_tool_use_extracted(self):
        p = _provider(post_resp=_ok_response("Calling tool.", tool_name="bash"))
        result = await p.execute(_task(), _manifest())
        self.assertEqual(len(result.tool_results), 1)
        self.assertEqual(result.tool_results[0].tool_name, "bash")
        self.assertEqual(result.tool_results[0].tool_input["param"], "value")

    async def test_execute_failed_on_non_200(self):
        p = _provider(post_status=400, post_resp={"error": {"message": "bad request"}})
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.FAILED)
        self.assertIn("400", result.reason)

    async def test_execute_text_and_tool_together(self):
        resp = _ok_response(text="Let me call a tool.", tool_name="search")
        p = _provider(post_resp=resp)
        result = await p.execute(_task(), _manifest())
        self.assertIsNotNone(result.output)
        self.assertEqual(len(result.tool_results), 1)


if __name__ == "__main__":
    unittest.main()
