"""
tasker.workers.providers.anthropic
------------------------------------
AnthropicProvider -- Anthropic Messages API.
See SDD Section 5.6.2.
"""
from __future__ import annotations

import time
from collections.abc import Awaitable, Callable

from tasker.tools.normalizer import ToolCallNormalizer
from tasker.workers.base import (
    ModelUsage,
    ProviderType,
    WorkerManifest,
    WorkerResult,
    WorkerStatus,
    WorkerTask,
)
from tasker.workers.providers.base import WorkerProviderBase

_PostFn = Callable[[str, dict, dict], Awaitable[tuple[int, dict]]]
_GetFn = Callable[[str, dict], Awaitable[tuple[int, dict]]]

_ANTHROPIC_VERSION = "2023-06-01"
_DEFAULT_MAX_TOKENS = 4096


def _build_anthropic_request(
    task: WorkerTask,
    worker: WorkerManifest,
) -> dict:
    system = task.context.get("system_prompt", "")
    messages: list[dict] = list(task.context.get("messages", []))
    messages.append({"role": "user", "content": task.instruction})

    tools = ToolCallNormalizer.format_tools(task.tools, worker.tool_protocol)
    # Anthropic uses "input_schema" instead of "parameters"
    anthropic_tools = [
        {
            "name": t["function"]["name"],
            "description": t["function"]["description"],
            "input_schema": t["function"]["parameters"],
        }
        for t in tools
    ]

    payload: dict = {
        "model": worker.model_id,
        "max_tokens": task.context.get("max_tokens", _DEFAULT_MAX_TOKENS),
        "messages": messages,
    }
    if system:
        payload["system"] = system
    if anthropic_tools:
        payload["tools"] = anthropic_tools
    return payload


def _parse_content(content: list[dict]) -> tuple[str, list[dict]]:
    """Split Anthropic content array into (text, tool_use_blocks_as_openai_calls)."""
    text_parts = []
    native_calls = []
    for i, block in enumerate(content):
        if block.get("type") == "text":
            text_parts.append(block.get("text", ""))
        elif block.get("type") == "tool_use":
            import json
            native_calls.append({
                "id": block.get("id", f"call_{i}"),
                "type": "function",
                "function": {
                    "name": block.get("name", ""),
                    "arguments": json.dumps(block.get("input", {})),
                },
            })
    return "\n".join(text_parts).strip(), native_calls


class AnthropicProvider(WorkerProviderBase):
    """
    Provider for Anthropic Claude models via the Messages API.
    Uses native tool_calls protocol (content-block format).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.anthropic.com",
        *,
        _post_fn: _PostFn | None = None,
        _get_fn: _GetFn | None = None,
    ) -> None:
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._post_fn = _post_fn or self._default_post
        self._get_fn = _get_fn or self._default_get

    def _headers(self) -> dict:
        return {
            "x-api-key": self._api_key,
            "anthropic-version": _ANTHROPIC_VERSION,
            "content-type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # WorkerProviderBase contract
    # ------------------------------------------------------------------ #

    def supports(self, worker: WorkerManifest) -> bool:
        return worker.provider == ProviderType.ANTHROPIC

    async def health_check(self, worker: WorkerManifest) -> bool:
        try:
            status, data = await self._get_fn(
                f"{self._base_url}/v1/models", self._headers()
            )
            if status not in (200, 401):
                return False
            if status == 200:
                model_ids = [m.get("id", "") for m in data.get("data", [])]
                return worker.model_id in model_ids
            return True  # 401 means reachable, key issue is separate
        except Exception:
            return False

    async def execute(self, task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
        start = time.monotonic()
        payload = _build_anthropic_request(task, worker)

        status, data = await self._post_fn(
            f"{self._base_url}/v1/messages",
            payload,
            self._headers(),
        )

        if status != 200:
            return WorkerResult(
                task_id=task.task_id,
                worker_id=worker.id,
                status=WorkerStatus.FAILED,
                output=None,
                tool_results=[],
                usage=ModelUsage(0, 0, 0.0),
                duration_ms=int((time.monotonic() - start) * 1000),
                reason=f"HTTP {status}: {data.get('error', {}).get('message', '')}",
            )

        content_blocks: list[dict] = data.get("content", [])
        text, native_calls = _parse_content(content_blocks)
        tool_results = ToolCallNormalizer.extract(text, native_calls, worker.tool_protocol)

        usage_data = data.get("usage", {})
        input_tok = usage_data.get("input_tokens", 0)
        output_tok = usage_data.get("output_tokens", 0)
        cost = (
            input_tok * worker.cost_input / 1_000_000
            + output_tok * worker.cost_output / 1_000_000
        )
        return WorkerResult(
            task_id=task.task_id,
            worker_id=worker.id,
            status=WorkerStatus.SUCCESS,
            output=text or None,
            tool_results=tool_results,
            usage=ModelUsage(input_tok, output_tok, cost),
            duration_ms=int((time.monotonic() - start) * 1000),
        )

    # ------------------------------------------------------------------ #
    # Default HTTP
    # ------------------------------------------------------------------ #

    async def _default_post(self, url: str, payload: dict, headers: dict) -> tuple[int, dict]:
        import aiohttp
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.post(
                url, json=payload, timeout=aiohttp.ClientTimeout(total=120)
            ) as resp:
                return resp.status, await resp.json()

    async def _default_get(self, url: str, headers: dict) -> tuple[int, dict]:
        import aiohttp
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                url, timeout=aiohttp.ClientTimeout(total=10)
            ) as resp:
                return resp.status, await resp.json()
