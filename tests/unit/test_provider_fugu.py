"""
Unit tests -- FuguProvider (tasker/workers/providers/fugu.py)
Phase 4 -- SDD Section 5.6.4
All HTTP is mocked via _post_fn / _get_fn injection.
"""
import unittest

from tasker.workers.base import (
    AgentRole,
    Capability,
    ComputeLocation,
    LatencyClass,
    PrivacyTier,
    ProviderType,
    RoutingPolicy,
    ToolProtocol,
    WorkerManifest,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.fugu import FuguProvider


# ------------------------------------------------------------------ #
# Fixtures
# ------------------------------------------------------------------ #

def _manifest(model_id: str = "fugu-8x22b") -> WorkerManifest:
    return WorkerManifest(
        id="fugu-w1",
        provider=ProviderType.FUGU,
        model_id=model_id,
        compute_location=ComputeLocation.DIRECT_CLOUD,
        capabilities={Capability.TOOL_USE, Capability.MULTI_AGENT},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=65536,
        cost_input=5.0,
        cost_output=15.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.SLOW,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


def _task(instruction: str = "solve complex task") -> WorkerTask:
    return WorkerTask(
        task_id="t-004",
        step_index=0,
        role=AgentRole.WORKER,
        instruction=instruction,
        tools=[],
        context={},
        routing_policy=RoutingPolicy.CAPABILITY_FIRST,
        privacy_tier=PrivacyTier.ANY_CLOUD,
    )


def _ok_response(content: str = "Fugu synthesized result.") -> dict:
    return {
        "id": "chatcmpl-fugu-001",
        "choices": [{
            "message": {
                "role": "assistant",
                "content": content,
                "tool_calls": None,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 500,
            "completion_tokens": 200,
            "total_tokens": 700,
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
    return FuguProvider(
        api_key="fugu-key",
        _post_fn=_make_post(post_status, post_resp or _ok_response()),
        _get_fn=_make_get(get_status, get_resp or {"data": []}),
    )


# ------------------------------------------------------------------ #
# Tests
# ------------------------------------------------------------------ #

class TestFuguProviderSupports(unittest.TestCase):

    def test_supports_fugu_multi_agent(self):
        p = _provider()
        self.assertTrue(p.supports(_manifest()))

    def test_does_not_support_openai_provider(self):
        p = _provider()
        w = _manifest()
        w.provider = ProviderType.OPENAI
        self.assertFalse(p.supports(w))

    def test_does_not_support_fugu_without_multi_agent(self):
        p = _provider()
        w = WorkerManifest(
            id="fugu-no-ma",
            provider=ProviderType.FUGU,
            model_id="fugu-8x22b",
            compute_location=ComputeLocation.DIRECT_CLOUD,
            capabilities={Capability.TOOL_USE},  # missing MULTI_AGENT
            tool_protocol=ToolProtocol.NATIVE,
            context_window=65536,
            cost_input=0.0,
            cost_output=0.0,
            ollama_usage_level=None,
            latency_class=LatencyClass.SLOW,
            available=True,
            requires_gpu=False,
            vram_mb=None,
        )
        self.assertFalse(p.supports(w))


class TestFuguProviderExecute(unittest.IsolatedAsyncioTestCase):

    async def test_execute_success(self):
        p = _provider(post_resp=_ok_response("Fugu result here."))
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertEqual(result.output, "Fugu result here.")

    async def test_execute_usage_tracked(self):
        p = _provider()
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.usage.input_tokens, 500)
        self.assertEqual(result.usage.output_tokens, 200)

    async def test_execute_failed_on_non_200(self):
        p = _provider(post_status=503, post_resp={"error": {"message": "overloaded"}})
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.FAILED)

    async def test_execute_uses_fugu_endpoint(self):
        captured: list[str] = []

        async def _recording_post(url: str, payload: dict, headers: dict) -> tuple[int, dict]:
            captured.append(url)
            return 200, _ok_response()

        p = FuguProvider(
            api_key="key",
            base_url="https://api.sakana.ai/v1",
            _post_fn=_recording_post,
            _get_fn=_make_get(200, {}),
        )
        await p.execute(_task(), _manifest())
        self.assertIn("sakana.ai", captured[0])

    async def test_fugu_treated_as_opaque_single_step(self):
        """Fugu returns a synthesized result; harness does not see sub-agents."""
        p = _provider(post_resp=_ok_response("Synthesized by Fugu internally."))
        result = await p.execute(_task("solve a complex reasoning task"), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertIsNotNone(result.output)
        # No tool results expected — Fugu is opaque
        self.assertEqual(result.tool_results, [])


if __name__ == "__main__":
    unittest.main()
