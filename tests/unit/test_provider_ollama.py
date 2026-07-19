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
from tasker.workers.providers.ollama import OllamaProvider, format_tool_result_message


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


def _task(
    instruction: str = "say hello",
    tools: list | None = None,
    context: dict | None = None,
) -> WorkerTask:
    return WorkerTask(
        task_id="t-001",
        step_index=0,
        role=AgentRole.WORKER,
        instruction=instruction,
        tools=tools or [],
        context=context if context is not None else {},
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


def _thinking_empty_response(
    thinking: str = "reasoned to an answer but never emitted it",
    done_reason: str = "stop",
) -> dict:
    """A response matching the 'answer lost inside <think>' signature."""
    return {
        "model": "lfm2.5-thinking:latest",
        "message": {
            "role": "assistant",
            "content": "",
            "thinking": thinking,
        },
        "prompt_eval_count": 50,
        "eval_count": 20,
        "done": True,
        "done_reason": done_reason,
    }


def _make_post_sequence(responses: list[tuple[int, dict]], captured: list | None = None):
    """Returns a different (status, response) pair on each successive call."""
    calls = {"n": 0}

    async def _post(url: str, payload: dict) -> tuple[int, dict]:
        payload.pop("_timeout", None)
        if captured is not None:
            captured.append(payload)
        i = min(calls["n"], len(responses) - 1)
        calls["n"] += 1
        return responses[i]
    return _post


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


class TestOllamaProviderEmptyContentRetry(unittest.IsolatedAsyncioTestCase):
    """
    Reasoning models (lfm2.5-thinking) sometimes emit a stop token right
    after closing <think> without ever producing content. Confirmed live
    on Designlab1 to be sampling-dependent, not deterministic. Provider
    retries identical requests up to _EMPTY_CONTENT_MAX_RETRIES times
    when it sees the signature: empty content + non-empty thinking +
    done_reason == "stop".
    """

    async def test_retries_and_succeeds_on_second_attempt(self):
        captured: list = []
        post = _make_post_sequence(
            [
                (200, _thinking_empty_response()),
                (200, _ok_response("recovered answer")),
            ],
            captured,
        )
        p = OllamaProvider(base_url="http://localhost:11434", _post_fn=post)
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertEqual(result.output, "recovered answer")
        self.assertEqual(len(captured), 2)

    async def test_exhausts_retries_and_returns_empty_content(self):
        captured: list = []
        # 1 initial attempt + _EMPTY_CONTENT_MAX_RETRIES retries, all empty
        responses = [(200, _thinking_empty_response())] * 4
        post = _make_post_sequence(responses, captured)
        p = OllamaProvider(base_url="http://localhost:11434", _post_fn=post)
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertIsNone(result.output)
        self.assertEqual(len(captured), 1 + p._EMPTY_CONTENT_MAX_RETRIES)

    async def test_does_not_retry_when_thinking_absent(self):
        """Empty content with no thinking field is a different failure mode -- not retried."""
        captured: list = []
        resp = _ok_response(content="")
        post = _make_post_sequence([(200, resp)], captured)
        p = OllamaProvider(base_url="http://localhost:11434", _post_fn=post)
        await p.execute(_task(), _manifest())
        self.assertEqual(len(captured), 1)

    async def test_does_not_retry_when_done_reason_is_not_stop(self):
        """done_reason=='length' means real truncation -- retrying identically won't help."""
        captured: list = []
        resp = _thinking_empty_response(done_reason="length")
        post = _make_post_sequence([(200, resp)], captured)
        p = OllamaProvider(base_url="http://localhost:11434", _post_fn=post)
        await p.execute(_task(), _manifest())
        self.assertEqual(len(captured), 1)

    async def test_does_not_retry_when_tool_calls_present(self):
        """
        A native tool call from a thinking model legitimately has empty
        content + non-empty thinking + tool_calls[] -- that's an answer,
        not a lost one. Found live by the Phase 8.2 readiness probe, which
        burned 2 extra calls per native probe before this guard.
        """
        captured: list = []
        resp = _thinking_empty_response()
        resp["message"]["tool_calls"] = [
            {"function": {"name": "get_current_time",
                          "arguments": {"timezone": "America/Chicago"}}}
        ]
        post = _make_post_sequence([(200, resp)], captured)
        p = OllamaProvider(base_url="http://localhost:11434", _post_fn=post)
        result = await p.execute(_task(), _manifest())
        self.assertEqual(len(captured), 1)
        self.assertEqual(result.tool_results[0].tool_name, "get_current_time")


class TestOllamaProviderMultiTurn(unittest.IsolatedAsyncioTestCase):
    """
    Building blocks for tasker/tools/loop.py's multi-turn tool loop:
    raw_assistant_message replay, continuation-turn message building, and
    tool_call_id threading through format_tool_result_message.
    """

    async def test_raw_assistant_message_native_includes_tool_calls(self):
        resp = _ok_response(
            content="",
            tool_calls=[{"function": {"name": "bash", "arguments": {"command": "ls"}}}],
        )
        p = _provider(post_response=resp)
        result = await p.execute(_task(), _manifest())
        self.assertEqual(result.raw_assistant_message["role"], "assistant")
        self.assertEqual(result.raw_assistant_message["content"], "")
        self.assertEqual(
            result.raw_assistant_message["tool_calls"][0]["function"]["name"], "bash"
        )

    async def test_raw_assistant_message_lfm25_is_content_only(self):
        resp = _ok_response(content='[{"name": "get_weather", "arguments": {"location": "Austin"}}]')
        p = _provider(post_response=resp)
        result = await p.execute(_task(), _lfm25_manifest())
        self.assertEqual(
            result.raw_assistant_message,
            {"role": "assistant", "content": resp["message"]["content"]},
        )
        self.assertNotIn("tool_calls", result.raw_assistant_message)

    async def test_build_messages_continuation_turn_does_not_duplicate_instruction(self):
        captured: list = []
        p = _provider(post_response=_ok_response("final answer"), captured_payloads=captured)
        history = [
            {"role": "user", "content": "List files in current directory"},
            {"role": "assistant", "content": '[{"name": "bash", "arguments": {"command": "ls"}}]'},
            {"role": "tool", "content": "file1.py\nfile2.py"},
        ]
        await p.execute(
            _task(instruction="List files in current directory", context={"messages": history}),
            _manifest(),
        )
        sent = captured[0]["messages"]
        user_turns = [m for m in sent if m["role"] == "user"]
        self.assertEqual(len(user_turns), 1)
        self.assertEqual(sent, history)


class TestFormatToolResultMessage(unittest.TestCase):

    def test_omits_tool_call_id_by_default(self):
        msg = format_tool_result_message("bash", "file1.py", role=None)
        self.assertNotIn("tool_call_id", msg)
        self.assertEqual(msg["role"], "tool")

    def test_includes_tool_call_id_when_given(self):
        msg = format_tool_result_message("bash", "file1.py", role="tool", tool_call_id="call_0")
        self.assertEqual(msg["tool_call_id"], "call_0")

    def test_respects_role_override(self):
        msg = format_tool_result_message("bash", "file1.py", role="user")
        self.assertEqual(msg["role"], "user")

    def test_dict_result_serialized_to_json(self):
        msg = format_tool_result_message("bash", {"stdout": "ok"}, role=None)
        self.assertEqual(json.loads(msg["content"]), {"stdout": "ok"})


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


class TestOllamaProviderBudgetRecording(unittest.IsolatedAsyncioTestCase):
    """
    Phase 8.1: an injected OllamaSessionBudget accumulates GPU-time units
    (wall-clock duration x ollama_usage_level) on every successful
    OLLAMA_CLOUD call, and never on LOCAL_HARDWARE calls.
    """

    def _budget(self):
        from datetime import datetime

        from tasker.session.budget import OllamaSessionBudget

        return OllamaSessionBudget(
            plan=OllamaPlan.PRO, window_start=datetime.now().astimezone()
        )

    def _provider_with_budget(self, budget, post_status=200, post_response=None):
        return OllamaProvider(
            base_url="http://localhost:11434",
            concurrency_mgr=None,
            budget=budget,
            _post_fn=_make_post(post_status, post_response or _ok_response()),
            _get_fn=_make_get(200, {"models": []}),
        )

    async def test_cloud_call_records_usage(self):
        budget = self._budget()
        p = self._provider_with_budget(budget)
        await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        self.assertGreater(budget.usage_consumed, 0.0)
        self.assertGreater(budget.weekly_usage_consumed, 0.0)

    async def test_local_call_records_nothing(self):
        budget = self._budget()
        p = self._provider_with_budget(budget)
        await p.execute(_task(), _manifest(ComputeLocation.LOCAL_HARDWARE))
        self.assertEqual(budget.usage_consumed, 0.0)

    async def test_failed_cloud_call_records_nothing(self):
        budget = self._budget()
        p = self._provider_with_budget(budget, post_status=500, post_response={})
        await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        self.assertEqual(budget.usage_consumed, 0.0)

    def test_usage_units_scale_with_usage_level(self):
        from tasker.workers.providers.ollama import compute_usage_units

        self.assertEqual(compute_usage_units(10.0, OllamaUsageLevel.LIGHT), 10.0)
        self.assertEqual(compute_usage_units(10.0, OllamaUsageLevel.HEAVY), 30.0)
        self.assertEqual(compute_usage_units(10.0, OllamaUsageLevel.EXTRA_HEAVY), 40.0)

    def test_usage_units_none_level_billed_as_light(self):
        from tasker.workers.providers.ollama import compute_usage_units

        self.assertEqual(compute_usage_units(7.5, None), 7.5)

    async def test_usage_level_none_billed_as_light(self):
        # The ad-hoc orchestrator manifest has ollama_usage_level=None;
        # it must still consume budget (conservatively as level 1).
        budget = self._budget()
        m = _manifest(ComputeLocation.OLLAMA_CLOUD)
        m.ollama_usage_level = None
        await self._provider_with_budget(budget).execute(_task(), m)
        self.assertGreater(budget.usage_consumed, 0.0)

    async def test_no_budget_injected_is_fine(self):
        p = _provider(post_response=_ok_response())
        result = await p.execute(_task(), _manifest(ComputeLocation.OLLAMA_CLOUD))
        self.assertEqual(result.status, WorkerStatus.SUCCESS)


if __name__ == "__main__":
    unittest.main()
