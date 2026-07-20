"""
Unit tests -- multi-turn tool loop (tasker/tools/loop.py)

Real tool execution (tasker/tools/executor.py) is unit-tested separately
in test_tool_executor.py -- these tests mock execute_tool() to isolate
the loop's own control flow (turn counting, message threading,
accumulation, DEFERRED handling). One integration test at the bottom
uses the real OllamaProvider (HTTP mocked) to catch bugs at the seam
between the two modules that a fully-isolated unit test would miss.
"""
import unittest
from pathlib import Path
from unittest import mock

from tasker.tools.loop import _MAX_TOOL_TURNS, run_tool_loop
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
from tasker.workers.providers.ollama import OllamaProvider


def _worker(
    tool_protocol: ToolProtocol = ToolProtocol.LFM25,
    tool_result_role: str | None = "tool",
    compute_location: ComputeLocation = ComputeLocation.LOCAL_HARDWARE,
) -> WorkerManifest:
    return WorkerManifest(
        id="w1",
        provider=ProviderType.OLLAMA,
        model_id="lfm2.5-thinking:latest",
        compute_location=compute_location,
        capabilities={Capability.TOOL_USE},
        tool_protocol=tool_protocol,
        context_window=32768,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
        tool_result_role=tool_result_role,
    )


def _task(instruction: str = "List files", context: dict | None = None, tools: list | None = None) -> WorkerTask:
    return WorkerTask(
        task_id="t1",
        step_index=0,
        role=AgentRole.WORKER,
        instruction=instruction,
        tools=tools or [],
        context=context or {},
        routing_policy=RoutingPolicy.COST_OPTIMIZED,
        privacy_tier=PrivacyTier.LOCAL_ONLY,
    )


def _result(
    status: WorkerStatus = WorkerStatus.SUCCESS,
    output: str | None = None,
    tool_results: list | None = None,
    raw_assistant_message: dict | None = None,
    usage: ModelUsage | None = None,
    duration_ms: int = 100,
) -> WorkerResult:
    return WorkerResult(
        task_id="t1",
        worker_id="w1",
        status=status,
        output=output,
        tool_results=tool_results or [],
        usage=usage or ModelUsage(10, 5, 0.0),
        duration_ms=duration_ms,
        raw_assistant_message=raw_assistant_message,
    )


class FakeProvider(WorkerProviderBase):
    """Returns scripted WorkerResults in sequence; records every WorkerTask received."""

    def __init__(self, results: list[WorkerResult]):
        self._results = list(results)
        self.calls: list[WorkerTask] = []

    async def execute(self, task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
        self.calls.append(task)
        i = min(len(self.calls) - 1, len(self._results) - 1)
        return self._results[i]

    async def health_check(self, worker: WorkerManifest) -> bool:
        return True

    def supports(self, worker: WorkerManifest) -> bool:
        return True


class TestRunToolLoop(unittest.IsolatedAsyncioTestCase):

    async def test_single_turn_no_tools_passthrough(self):
        provider = FakeProvider([_result(output="final answer")])
        result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(result.output, "final answer")
        self.assertEqual(len(provider.calls), 1)
        self.assertEqual(result.tool_results, [])

    async def test_two_turn_happy_path_executes_and_accumulates(self):
        requested = WorkerToolResult("bash", {"command": "ls"}, None, None, 0)
        executed = WorkerToolResult("bash", {"command": "ls"}, "file1.py\nfile2.py", None, 5)

        provider = FakeProvider([
            _result(
                output="",
                tool_results=[requested],
                raw_assistant_message={
                    "role": "assistant",
                    "content": '[{"name":"bash","arguments":{"command":"ls"}}]',
                },
            ),
            _result(output="The files are file1.py and file2.py"),
        ])
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))

        self.assertEqual(result.output, "The files are file1.py and file2.py")
        self.assertEqual(result.tool_results, [executed])
        self.assertEqual(len(provider.calls), 2)

        # Design review bug #3: running_messages must never contain a
        # role:"system" entry, and the original user instruction must not
        # be duplicated on the continuation turn.
        turn2_messages = provider.calls[1].context["messages"]
        self.assertTrue(all(m["role"] != "system" for m in turn2_messages))
        self.assertEqual(turn2_messages[0], {"role": "user", "content": "List files"})
        self.assertEqual(turn2_messages[1]["role"], "assistant")
        self.assertEqual(turn2_messages[2], {"role": "tool", "content": "file1.py\nfile2.py"})

    async def test_multiple_tool_calls_in_one_turn_execute_in_parallel(self):
        # SDD 5.1a "parallel fetch": a turn requesting N tool calls (e.g.
        # multiple retrieve calls) must run them concurrently, not one at
        # a time -- proven by wall-clock time staying close to a single
        # call's delay rather than growing with N.
        import asyncio
        import time

        requested = [
            WorkerToolResult("retrieve", {"url": f"https://example.com/{i}"}, None, None, 0)
            for i in range(3)
        ]
        provider = FakeProvider([
            _result(
                output="", tool_results=list(requested),
                raw_assistant_message={"role": "assistant", "content": "..."},
            ),
            _result(output="done"),
        ])

        async def slow_execute_tool(tr, *, worker, cwd, delegation=None):
            await asyncio.sleep(0.15)
            return WorkerToolResult(tr.tool_name, tr.tool_input, "ok", None, 150)

        with mock.patch("tasker.tools.loop.execute_tool", side_effect=slow_execute_tool):
            start = time.monotonic()
            await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
            elapsed = time.monotonic() - start

        # Sequential would take >= 0.45s (3 x 0.15s); parallel stays near 0.15s.
        self.assertLess(elapsed, 0.35)

    async def test_usage_and_duration_accumulate_across_turns(self):
        requested = WorkerToolResult("bash", {"command": "ls"}, None, None, 0)
        executed = WorkerToolResult("bash", {"command": "ls"}, "ok", None, 5)
        provider = FakeProvider([
            _result(output="", tool_results=[requested], usage=ModelUsage(10, 5, 0.01), duration_ms=100,
                     raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="done", usage=ModelUsage(20, 8, 0.02), duration_ms=150),
        ])
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(result.usage.input_tokens, 30)
        self.assertEqual(result.usage.output_tokens, 13)
        self.assertAlmostEqual(result.usage.cost_usd, 0.03)
        self.assertEqual(result.duration_ms, 100 + 150 + 5)  # + the executed tool's own duration

    async def test_max_turns_exhaustion_returns_last_result_with_warning(self):
        # Task 8.3 verification: max_turns is a HARD cap on provider calls.
        # Each turn requests a *different* command so the repeated-identical-
        # call guard (tested separately below) never fires and the cap is
        # what terminates the loop.
        wants = [
            _result(
                output="",
                tool_results=[WorkerToolResult("bash", {"command": f"ls {i}"}, None, None, 0)],
                raw_assistant_message={"role": "assistant", "content": "..."},
            )
            for i in range(_MAX_TOOL_TURNS + 2)
        ]
        provider = FakeProvider(wants)
        with mock.patch("tasker.tools.loop.execute_tool") as mock_execute:
            mock_execute.return_value = WorkerToolResult("bash", {"command": "ls"}, "output", None, 5)
            with self.assertLogs("tasker.tools.loop", level="WARNING") as cm:
                result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(len(provider.calls), _MAX_TOOL_TURNS)
        self.assertIn("max_turns", "\n".join(cm.output))
        # The final (unexecuted) pending request survives into tool_results
        last_pending = wants[_MAX_TOOL_TURNS - 1].tool_results[0]
        self.assertIn(last_pending, result.tool_results)

    async def test_identical_consecutive_calls_terminate_early(self):
        # Task 8.3 guard: turn 2 re-requests exactly the same call as turn 1
        # -> loop stops at turn 2, well before max_turns, without executing
        # the duplicate.
        pending = WorkerToolResult("bash", {"command": "ls"}, None, None, 0)
        always_wants_same = _result(
            output="", tool_results=[pending],
            raw_assistant_message={"role": "assistant", "content": "..."},
        )
        provider = FakeProvider([always_wants_same] * (_MAX_TOOL_TURNS + 2))
        executed = WorkerToolResult("bash", {"command": "ls"}, "output", None, 5)
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed) as mock_execute:
            with self.assertLogs("tasker.tools.loop", level="WARNING") as cm:
                result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(len(provider.calls), 2)          # not _MAX_TOOL_TURNS
        self.assertEqual(mock_execute.call_count, 1)      # duplicate never executed
        self.assertIn("identical tool call", "\n".join(cm.output))
        # Turn 1's executed result and turn 2's unexecuted request both survive
        self.assertIn(executed, result.tool_results)
        self.assertIn(pending, result.tool_results)

    async def test_same_tool_different_args_is_not_a_repeat(self):
        # bash ls -> bash pwd -> final answer: same tool, different
        # arguments -- must NOT trigger the guard.
        provider = FakeProvider([
            _result(output="", tool_results=[WorkerToolResult("bash", {"command": "ls"}, None, None, 0)],
                    raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="", tool_results=[WorkerToolResult("bash", {"command": "pwd"}, None, None, 0)],
                    raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="done"),
        ])
        executed = WorkerToolResult("bash", {"command": "x"}, "output", None, 5)
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(len(provider.calls), 3)
        self.assertEqual(result.output, "done")

    async def test_nonconsecutive_repeat_is_allowed(self):
        # ls -> pwd -> ls -> final: repeating a call later in the task is
        # legitimate (e.g. re-checking state after a change); only
        # *consecutive* identical requests terminate the loop.
        ls_req = WorkerToolResult("bash", {"command": "ls"}, None, None, 0)
        pwd_req = WorkerToolResult("bash", {"command": "pwd"}, None, None, 0)
        provider = FakeProvider([
            _result(output="", tool_results=[ls_req],
                    raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="", tool_results=[pwd_req],
                    raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="", tool_results=[ls_req],
                    raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="done"),
        ])
        executed = WorkerToolResult("bash", {"command": "x"}, "output", None, 5)
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(len(provider.calls), 4)
        self.assertEqual(result.output, "done")

    async def test_identical_multi_call_set_terminates_early(self):
        # The guard compares the whole requested set: two calls repeated
        # identically as a pair on the next turn -> terminate.
        pair = [
            WorkerToolResult("bash", {"command": "ls"}, None, None, 0),
            WorkerToolResult("file_read", {"path": "a.txt"}, None, None, 0),
        ]
        wants_pair = _result(
            output="", tool_results=list(pair),
            raw_assistant_message={"role": "assistant", "content": "..."},
        )
        provider = FakeProvider([wants_pair, wants_pair, _result(output="never reached")])
        executed = WorkerToolResult("bash", {"command": "x"}, "output", None, 5)
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed) as mock_execute:
            with self.assertLogs("tasker.tools.loop", level="WARNING"):
                result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(len(provider.calls), 2)
        self.assertEqual(mock_execute.call_count, 2)      # only turn 1's pair ran

    async def test_tool_execution_error_fed_back_as_content_and_loop_continues(self):
        requested = WorkerToolResult("bash", {"command": "sleep 100"}, None, None, 0)
        errored = WorkerToolResult("bash", {"command": "sleep 100"}, None, "timed out after 30.0s", 30000)
        provider = FakeProvider([
            _result(output="", tool_results=[requested],
                     raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(output="It looks like that timed out."),
        ])
        with mock.patch("tasker.tools.loop.execute_tool", return_value=errored):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(result.output, "It looks like that timed out.")
        self.assertEqual(len(provider.calls), 2)
        turn2_messages = provider.calls[1].context["messages"]
        self.assertIn("ERROR: timed out after 30.0s", turn2_messages[-1]["content"])

    async def test_non_success_status_preserves_prior_accumulated_tool_results(self):
        requested = WorkerToolResult("bash", {"command": "ls"}, None, None, 0)
        executed = WorkerToolResult("bash", {"command": "ls"}, "file1.py", None, 5)
        provider = FakeProvider([
            _result(output="", tool_results=[requested],
                     raw_assistant_message={"role": "assistant", "content": "..."}),
            _result(status=WorkerStatus.FAILED, output=None, tool_results=[]),
        ])
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(result.status, WorkerStatus.FAILED)
        self.assertIn(executed, result.tool_results)

    async def test_deferred_retries_then_succeeds(self):
        provider = FakeProvider([
            _result(status=WorkerStatus.DEFERRED, output=None),
            _result(status=WorkerStatus.DEFERRED, output=None),
            _result(output="answered after retry"),
        ])
        with mock.patch("tasker.tools.loop._DEFERRED_BACKOFF_S", 0.001):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(result.status, WorkerStatus.SUCCESS)
        self.assertEqual(result.output, "answered after retry")
        self.assertEqual(len(provider.calls), 3)

    async def test_deferred_exhausts_retries_returns_deferred(self):
        provider = FakeProvider([_result(status=WorkerStatus.DEFERRED, output=None)] * 5)
        with mock.patch("tasker.tools.loop._DEFERRED_BACKOFF_S", 0.001):
            result = await run_tool_loop(_task(), _worker(), provider, cwd=Path("."))
        self.assertEqual(result.status, WorkerStatus.DEFERRED)
        self.assertEqual(len(provider.calls), 3)  # _DEFERRED_MAX_RETRIES

    async def test_native_protocol_tool_call_id_threaded(self):
        requested = WorkerToolResult("bash", {"command": "ls"}, None, None, 0)
        executed = WorkerToolResult("bash", {"command": "ls"}, "file1.py", None, 5)
        provider = FakeProvider([
            _result(
                output="", tool_results=[requested],
                raw_assistant_message={
                    "role": "assistant", "content": "",
                    "tool_calls": [{"id": "call_0", "type": "function",
                                     "function": {"name": "bash", "arguments": "{}"}}],
                },
            ),
            _result(output="done"),
        ])
        with mock.patch("tasker.tools.loop.execute_tool", return_value=executed):
            await run_tool_loop(
                _task(), _worker(tool_protocol=ToolProtocol.NATIVE), provider, cwd=Path("."),
            )
        turn2_messages = provider.calls[1].context["messages"]
        self.assertEqual(turn2_messages[-1]["tool_call_id"], "call_0")

    async def test_seeds_history_from_task_context_when_present(self):
        """If a caller already provides context['messages'], the loop
        trusts it instead of re-seeding from task.instruction."""
        history = [{"role": "user", "content": "earlier turn"}]
        provider = FakeProvider([_result(output="answer")])
        await run_tool_loop(_task(context={"messages": history}), _worker(), provider, cwd=Path("."))
        self.assertEqual(provider.calls[0].context["messages"], history)


class TestRunToolLoopSystemMessageIntegration(unittest.IsolatedAsyncioTestCase):
    """
    Uses the REAL OllamaProvider (HTTP mocked only) so the loop's message
    threading interacts with OllamaProvider's actual _build_messages()/
    inject_tools() -- catches the system-message duplication bug (design
    review finding #3) that a loop-only or provider-only unit test would
    each miss individually.
    """

    async def test_tool_list_suffix_not_duplicated_across_turns(self):
        from tasker.workers.base import ToolDefinition

        tools = [ToolDefinition(
            name="bash", description="run a shell command",
            parameters={"type": "object", "properties": {"command": {"type": "string"}}},
        )]
        responses = [
            {
                "message": {"role": "assistant", "content": '[{"name": "bash", "arguments": {"command": "ls"}}]'},
                "prompt_eval_count": 50, "eval_count": 20, "done": True, "done_reason": "stop",
            },
            {
                "message": {"role": "assistant", "content": "Here are the files."},
                "prompt_eval_count": 60, "eval_count": 10, "done": True, "done_reason": "stop",
            },
        ]
        captured: list = []

        async def _post(url, payload):
            payload.pop("_timeout", None)
            captured.append(payload)
            return 200, responses[len(captured) - 1]

        provider = OllamaProvider(base_url="http://localhost:11434", _post_fn=_post)
        worker = _worker()
        task = WorkerTask(
            task_id="t1", step_index=0, role=AgentRole.WORKER, instruction="List files",
            tools=tools, context={"system_prompt": "You are a helpful coding assistant."},
            routing_policy=RoutingPolicy.COST_OPTIMIZED, privacy_tier=PrivacyTier.LOCAL_ONLY,
        )

        with mock.patch("tasker.tools.loop.execute_tool") as mock_execute:
            mock_execute.return_value = WorkerToolResult("bash", {"command": "ls"}, "file1.py", None, 5)
            result = await run_tool_loop(task, worker, provider, cwd=Path("."))

        self.assertEqual(result.output, "Here are the files.")
        self.assertEqual(len(captured), 2)
        turn2_system_msgs = [m for m in captured[1]["messages"] if m["role"] == "system"]
        self.assertEqual(len(turn2_system_msgs), 1)
        self.assertEqual(turn2_system_msgs[0]["content"].count("List of tools:"), 1)


if __name__ == "__main__":
    unittest.main()
