"""
tasker.workers.providers.openai_provider
-----------------------------------------
OpenAIProvider -- OpenAI Chat Completions API.
See SDD Section 5.6.3.
"""
from __future__ import annotations

import json
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


def _build_openai_request(task: WorkerTask, worker: WorkerManifest) -> dict:
    messages: list[dict] = []
    if sp := task.context.get("system_prompt"):
        messages.append({"role": "system", "content": sp})
    for msg in task.context.get("messages", []):
        messages.append(msg)
    messages.append({"role": "user", "content": task.instruction})

    tools = ToolCallNormalizer.format_tools(task.tools, worker.tool_protocol)
    payload: dict = {
        "model": worker.model_id,
        "messages": messages,
    }
    if tools:
        payload["tools"] = tools
    return payload


class OpenAIProvider(WorkerProviderBase):
    """
    Provider for OpenAI-compatible Chat Completions API.
    Used for OpenAI models directly (see FuguProvider for Fugu/OpenRouter).
    """

    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com",
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
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    # ------------------------------------------------------------------ #
    # WorkerProviderBase contract
    # ------------------------------------------------------------------ #

    def supports(self, worker: WorkerManifest) -> bool:
        return worker.provider == ProviderType.OPENAI

    async def health_check(self, worker: WorkerManifest) -> bool:
        try:
            status, data = await self._get_fn(
                f"{self._base_url}/v1/models", self._headers()
            )
            if status == 200:
                model_ids = [m.get("id", "") for m in data.get("data", [])]
                return worker.model_id in model_ids
            return status in (200, 401)
        except Exception:
            return False

    async def execute(self, task: WorkerTask, worker: WorkerManifest) -> WorkerResult:
        start = time.monotonic()
        payload = _build_openai_request(task, worker)

        status, data = await self._post_fn(
            f"{self._base_url}/v1/chat/completions",
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

        choices = data.get("choices", [])
        msg = choices[0].get("message", {}) if choices else {}
        content: str = msg.get("content") or ""
        raw_calls: list[dict] = msg.get("tool_calls") or []

        # OpenAI tool_calls already in standard format; arguments is a JSON string
        tool_results = ToolCallNormalizer.extract(content, raw_calls, worker.tool_protocol)

        usage_data = data.get("usage", {})
        input_tok = usage_data.get("prompt_tokens", 0)
        output_tok = usage_data.get("completion_tokens", 0)
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
