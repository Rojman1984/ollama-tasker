"""
tasker.workers.providers.ollama
--------------------------------
OllamaProvider -- handles LOCAL_HARDWARE and OLLAMA_CLOUD.
Single provider, same endpoint, compute_location distinguishes them.
See SDD Section 5.6.1.
"""
from __future__ import annotations

import json
import logging
import time
from collections.abc import Awaitable, Callable

from tasker.session.budget import OllamaSessionBudget
from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.tools.normalizer import ToolCallNormalizer
from tasker.workers.base import (
    ComputeLocation,
    ModelUsage,
    OllamaQueueFullError,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase

logger = logging.getLogger(__name__)

# Callable types for HTTP injection (allows mocking without libraries)
_PostFn = Callable[[str, dict], Awaitable[tuple[int, dict]]]
_GetFn = Callable[[str], Awaitable[tuple[int, dict]]]


def _build_messages(task: WorkerTask) -> list[dict]:
    messages: list[dict] = []
    if sp := task.context.get("system_prompt"):
        messages.append({"role": "system", "content": sp})
    history = task.context.get("messages", [])
    messages.extend(history)
    # Only inject task.instruction as a fresh user turn on the first call
    # (empty history). A multi-turn tool loop (tasker/tools/loop.py) passes
    # a non-empty history that already ends with the right next message
    # (e.g. a tool result) -- re-appending the original instruction there
    # would duplicate it as if the user asked the same thing again.
    if not history:
        messages.append({"role": "user", "content": task.instruction})
    return messages


def _deferred(task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
    return WorkerResult(
        task_id=task.task_id,
        worker_id=worker.id,
        status=WorkerStatus.DEFERRED,
        output=None,
        tool_results=[],
        usage=ModelUsage(0, 0, 0.0),
        duration_ms=0,
        reason="No Ollama Cloud concurrency slot available.",
    )


def format_tool_result_message(
    tool_name: str,
    result: str | dict,
    role: str | None,
    tool_call_id: str | None = None,
) -> dict:
    """
    Build the message dict to append to the next turn's context['messages']
    after a tool executes, respecting WorkerManifest.tool_result_role.
    Consumed end-to-end by tasker/tools/loop.py's multi-turn tool loop.

    "tool" is the official role for tool results; Ollama has been observed
    to reject it for some LFM2-family models, requiring "user" as a
    workaround instead -- see SDD_ADDENDUM_7.5.md A.2b. role=None means
    "use the protocol default" ("tool" for LFM25, tested first).

    tool_call_id: for NATIVE protocol, the synthesized call_{i} id from the
    same turn's tool_calls[] (see OllamaProvider.execute), so the reply can
    be paired with its request. Ollama's own tool_calls response never
    includes an id itself (OllamaProvider invents call_{i} purely for
    OpenAI-format normalization), so it's unconfirmed whether Ollama's
    /api/chat enforces id-based pairing -- included when available as
    cheap insurance, omitted (dict key absent) otherwise. Not used for
    non-NATIVE protocols, which have no id concept.
    """
    content = result if isinstance(result, str) else json.dumps(result)
    msg = {"role": role or "tool", "content": content}
    if tool_call_id is not None:
        msg["tool_call_id"] = tool_call_id
    return msg


def compute_usage_units(elapsed_s: float, usage_level: int | None) -> float:
    """
    GPU-time units for one Ollama Cloud call (SDD 3.1: usage unit =
    GPU-time x model usage level 1-4). Wall-clock duration approximates
    GPU-time (Ollama reports no GPU seconds; wall clock is an upper bound
    that errs on the early-throttle side). usage_level None (e.g. the
    ad-hoc orchestrator manifest) is billed conservatively as LIGHT (1).
    """
    return elapsed_s * float(usage_level or 1)


def _error(task: WorkerTask, worker: WorkerManifest, reason: str, elapsed: float) -> WorkerResult:
    return WorkerResult(
        task_id=task.task_id,
        worker_id=worker.id,
        status=WorkerStatus.FAILED,
        output=None,
        tool_results=[],
        usage=ModelUsage(0, 0, 0.0),
        duration_ms=int(elapsed * 1000),
        reason=reason,
    )


class OllamaProvider(WorkerProviderBase):
    """
    Unified provider for LOCAL_HARDWARE and OLLAMA_CLOUD Ollama workers.

    - LOCAL_HARDWARE: direct call, no concurrency management
    - OLLAMA_CLOUD: acquires a slot from OllamaCloudConcurrencyManager;
      returns DEFERRED immediately if no slot is available;
      raises OllamaQueueFullError on HTTP 429
    """

    # Reasoning models (e.g. lfm2.5-thinking) occasionally emit a stop
    # token immediately after closing their <think> block without ever
    # producing post-think content, despite reasoning to a correct
    # conclusion internally. Confirmed live (Designlab1, Ollama 0.30.11,
    # lfm2.5-thinking:latest) to be sampling-dependent -- identical
    # requests sometimes succeed, sometimes don't. See execute()'s retry
    # loop and CLAUDE.md's "Current Session Notes" history for the
    # investigation that led here.
    _EMPTY_CONTENT_MAX_RETRIES = 2

    def __init__(
        self,
        base_url: str,
        concurrency_mgr: OllamaCloudConcurrencyManager | None = None,
        budget: OllamaSessionBudget | None = None,
        *,
        _post_fn: _PostFn | None = None,
        _get_fn: _GetFn | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._concurrency = concurrency_mgr
        self._budget = budget
        self._post_fn = _post_fn or self._default_post
        self._get_fn = _get_fn or self._default_get

    # ------------------------------------------------------------------ #
    # WorkerProviderBase contract
    # ------------------------------------------------------------------ #

    def supports(self, worker: WorkerManifest) -> bool:
        return worker.provider == ProviderType.OLLAMA

    async def health_check(self, worker: WorkerManifest) -> bool:
        try:
            status, data = await self._get_fn(f"{self._base_url}/api/tags")
            if status != 200:
                return False
            models = [m.get("name", "") for m in data.get("models", [])]
            return any(worker.model_id in m for m in models)
        except Exception:
            return False

    async def execute(self, task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
        is_cloud = worker.compute_location == ComputeLocation.OLLAMA_CLOUD
        acquired = False

        if is_cloud and self._concurrency:
            acquired = await self._concurrency.try_acquire()
            if not acquired:
                return _deferred(task, worker)

        start = time.monotonic()
        try:
            messages = _build_messages(task)

            # Protocol-aware tool routing. NATIVE: Ollama handles tool
            # calling transparently via tools[] -- never inject into the
            # system prompt. Everything else: Ollama rejects tools[] for
            # these model families (confirmed for LFM2.5 -- see
            # SDD_ADDENDUM_7.5.md A.2b), so tool definitions are injected
            # into the messages instead and tools[] is omitted entirely.
            ollama_tools: list[dict] | None = None
            if worker.tool_protocol == ToolProtocol.NATIVE:
                formatted = ToolCallNormalizer.format_tools(task.tools, worker.tool_protocol)
                if formatted:
                    ollama_tools = formatted
            elif task.tools:
                messages = ToolCallNormalizer.inject_tools(
                    messages, task.tools, worker.tool_protocol
                )

            payload: dict = {
                "model": worker.model_id,
                "messages": messages,
                "stream": False,
            }
            if ollama_tools:
                payload["tools"] = ollama_tools

            # 240s default: live-measured against lfm2.5-thinking:latest, a
            # single call routinely takes 90-120+s (heavy <think> output
            # even for trivial prompts) -- see factory.py's _make_call_model
            # for the measurement that motivated raising this from 120s.
            timeout = task.timeout_s or 240.0

            status, data = await self._post_fn(
                f"{self._base_url}/api/chat",
                {**payload, "_timeout": timeout},
            )

            if status == 429:
                raise OllamaQueueFullError(
                    f"Ollama queue full (HTTP 429) for {worker.model_id}"
                )
            if status != 200:
                return _error(task, worker, f"HTTP {status}", time.monotonic() - start)

            msg = data.get("message", {})
            content: str = msg.get("content") or ""

            # See _EMPTY_CONTENT_MAX_RETRIES docstring: retry identical
            # requests when the model's answer appears to have been lost
            # inside its <think> block. Signature: empty content + non-empty
            # thinking + a clean done_reason=="stop" (as opposed to e.g.
            # "length", which would mean real truncation, not this quirk)
            # + NO tool_calls -- a native tool call from a thinking model
            # legitimately has empty content alongside tool_calls[], and
            # retrying it would burn 2 extra (budgeted, if cloud) calls per
            # tool call. Found live by the Phase 8.2 readiness probe.
            retries = 0
            while (
                content == ""
                and msg.get("thinking")
                and not msg.get("tool_calls")
                and data.get("done_reason") == "stop"
                and retries < self._EMPTY_CONTENT_MAX_RETRIES
            ):
                retries += 1
                logger.warning(
                    "OllamaProvider: %s returned empty content with non-empty "
                    "thinking (done_reason=stop) -- retrying (%d/%d). instruction=%r",
                    worker.model_id, retries, self._EMPTY_CONTENT_MAX_RETRIES,
                    task.instruction[:80],
                )
                status, data = await self._post_fn(
                    f"{self._base_url}/api/chat",
                    {**payload, "_timeout": timeout},
                )
                if status == 429:
                    raise OllamaQueueFullError(
                        f"Ollama queue full (HTTP 429) for {worker.model_id}"
                    )
                if status != 200:
                    return _error(task, worker, f"HTTP {status}", time.monotonic() - start)
                msg = data.get("message", {})
                content = msg.get("content") or ""

            if content == "" and msg.get("thinking") and not msg.get("tool_calls"):
                logger.warning(
                    "OllamaProvider: %s exhausted %d retries with empty content "
                    "(thinking present, answer likely lost inside <think>). "
                    "instruction=%r",
                    worker.model_id, self._EMPTY_CONTENT_MAX_RETRIES,
                    task.instruction[:80],
                )

            if worker.tool_protocol == ToolProtocol.NATIVE:
                raw_calls: list[dict] = msg.get("tool_calls") or []
                # Ollama returns arguments as dict, not JSON string — normalise to OpenAI format
                native_calls = [
                    {
                        "id": f"call_{i}",
                        "type": "function",
                        "function": {
                            "name": c.get("function", {}).get("name", ""),
                            "arguments": json.dumps(
                                c.get("function", {}).get("arguments", {})
                            ),
                        },
                    }
                    for i, c in enumerate(raw_calls)
                ]
                tool_results = ToolCallNormalizer.extract(
                    content, native_calls, worker.tool_protocol
                )
            else:
                # Non-native protocols never get tool_calls[] from Ollama --
                # the model emits the call as text per the protocol's
                # output format, parsed by extract_tool_calls().
                tool_results = ToolCallNormalizer.extract_tool_calls(
                    content, worker.tool_protocol, tools=task.tools
                )
            input_tok = data.get("prompt_eval_count", 0)
            output_tok = data.get("eval_count", 0)
            cost = (
                input_tok * worker.cost_input / 1_000_000
                + output_tok * worker.cost_output / 1_000_000
            )
            # Replayable record of this turn's assistant message, for a
            # multi-turn tool loop (tasker/tools/loop.py) to append to
            # history verbatim on the next turn. "thinking" is deliberately
            # dropped -- reasoning models shouldn't be fed their own prior
            # <think> trace back as history (bloats context, encourages
            # re-reasoning instead of answering).
            raw_assistant_message: dict = {"role": "assistant", "content": content}
            if worker.tool_protocol == ToolProtocol.NATIVE and raw_calls:
                raw_assistant_message["tool_calls"] = raw_calls

            # Session budget accounting: only OLLAMA_CLOUD calls consume
            # budget; local inference is unlimited by plan (SDD 3.2).
            if is_cloud and self._budget is not None:
                elapsed_s = time.monotonic() - start
                units = compute_usage_units(elapsed_s, worker.ollama_usage_level)
                self._budget.record_usage(units)
                logger.info(
                    "OllamaCloud budget: +%.1f units (%s, %.1fs x level %s) -> "
                    "%.1f/%.0f session (%.1f%%)",
                    units, worker.model_id, elapsed_s,
                    worker.ollama_usage_level or 1,
                    self._budget.usage_consumed, self._budget.session_limit,
                    self._budget.usage_pct * 100,
                )

            return WorkerResult(
                task_id=task.task_id,
                worker_id=worker.id,
                status=WorkerStatus.SUCCESS,
                output=content or None,
                tool_results=tool_results,
                usage=ModelUsage(input_tok, output_tok, cost),
                duration_ms=int((time.monotonic() - start) * 1000),
                raw_assistant_message=raw_assistant_message,
            )

        finally:
            if acquired and self._concurrency:
                await self._concurrency.release()

    # ------------------------------------------------------------------ #
    # Default HTTP (uses aiohttp)
    # ------------------------------------------------------------------ #

    async def _default_post(self, url: str, payload: dict) -> tuple[int, dict]:
        import aiohttp
        timeout_s = payload.pop("_timeout", 240.0)
        async with aiohttp.ClientSession() as session:
            async with session.post(
                url,
                json=payload,
                timeout=aiohttp.ClientTimeout(total=timeout_s),
            ) as resp:
                return resp.status, await resp.json()

    async def _default_get(self, url: str) -> tuple[int, dict]:
        import aiohttp
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status, await resp.json()
