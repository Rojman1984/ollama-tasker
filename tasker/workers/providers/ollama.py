"""
tasker.workers.providers.ollama
--------------------------------
OllamaProvider -- handles LOCAL_HARDWARE and OLLAMA_CLOUD.
Single provider, same endpoint, compute_location distinguishes them.
See SDD Section 5.6.1.
"""
from __future__ import annotations

import json
import time
from collections.abc import Awaitable, Callable

from tasker.session.concurrency import OllamaCloudConcurrencyManager
from tasker.tools.normalizer import ToolCallNormalizer
from tasker.workers.base import (
    ComputeLocation,
    ModelUsage,
    OllamaQueueFullError,
    ProviderType,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase

# Callable types for HTTP injection (allows mocking without libraries)
_PostFn = Callable[[str, dict], Awaitable[tuple[int, dict]]]
_GetFn = Callable[[str], Awaitable[tuple[int, dict]]]


def _build_messages(task: WorkerTask) -> list[dict]:
    messages: list[dict] = []
    if sp := task.context.get("system_prompt"):
        messages.append({"role": "system", "content": sp})
    for msg in task.context.get("messages", []):
        messages.append(msg)
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

    def __init__(
        self,
        base_url: str,
        concurrency_mgr: OllamaCloudConcurrencyManager | None = None,
        *,
        _post_fn: _PostFn | None = None,
        _get_fn: _GetFn | None = None,
    ) -> None:
        self._base_url = base_url.rstrip("/")
        self._concurrency = concurrency_mgr
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
            tools = ToolCallNormalizer.format_tools(task.tools, worker.tool_protocol)
            payload: dict = {
                "model": worker.model_id,
                "messages": messages,
                "stream": False,
            }
            if tools:
                payload["tools"] = tools

            timeout = task.timeout_s or 120.0
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
            input_tok = data.get("prompt_eval_count", 0)
            output_tok = data.get("eval_count", 0)
            cost = (
                input_tok * worker.cost_input / 1_000_000
                + output_tok * worker.cost_output / 1_000_000
            )
            return WorkerResult(
                task_id=task.task_id,
                worker_id=worker.id,
                status=WorkerStatus.SUCCESS,
                output=content or None,
                tool_results=tool_results,
                usage=ModelUsage(input_tok, output_tok, cost),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        finally:
            if acquired and self._concurrency:
                await self._concurrency.release()

    # ------------------------------------------------------------------ #
    # Default HTTP (uses aiohttp)
    # ------------------------------------------------------------------ #

    async def _default_post(self, url: str, payload: dict) -> tuple[int, dict]:
        import aiohttp
        timeout_s = payload.pop("_timeout", 120.0)
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
