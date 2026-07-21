"""
tasker.tools.loop
-------------------
Multi-turn tool-execution loop: a worker requests a tool call, the
system runs it for real (tasker/tools/executor.py), the result is fed
back into the conversation, and the worker is re-invoked -- repeating
until it answers without requesting another tool, or max_turns is hit.

Lives outside tasker/orchestrator/ deliberately: "the orchestrator
never calls tools directly" is a hard rule (see
tasker/orchestrator/base.py's class docstring and CLAUDE.md's
non-negotiable constraint #5). This module is a worker-layer helper
that any orchestrator-driven caller (currently cli/shell.py) invokes
in place of a single provider.execute() call.

Coupled to OllamaProvider's format_tool_result_message() and
tool_call_id convention (see that function's docstring) -- reasonable
for now since OllamaProvider is the only provider actually wired into
cli/shell.py's provider_map. Revisit if/when Anthropic/OpenAI/Fugu
providers need their own multi-turn tool loop.
"""
from __future__ import annotations

import asyncio
import dataclasses
import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from tasker.runtime.delegation import DelegationContext
from tasker.tools.executor import execute_tool
from tasker.workers.base import ModelUsage, ToolProtocol, WorkerManifest, WorkerResult, WorkerStatus, WorkerTask, WorkerToolResult
from tasker.workers.providers.base import WorkerProviderBase
from tasker.workers.providers.ollama import format_tool_result_message

logger = logging.getLogger(__name__)

_MAX_TOOL_TURNS = 5
_DEFERRED_MAX_RETRIES = 3
_DEFERRED_BACKOFF_S = 0.5


async def _execute_with_deferred_retry(
    provider: WorkerProviderBase, task: WorkerTask, worker: WorkerManifest
) -> WorkerResult:
    """DEFERRED (no concurrency slot) is transient -- worth a short bounded
    wait rather than bailing immediately, especially once earlier turns
    have already produced real tool side effects."""
    result: WorkerResult | None = None
    for attempt in range(_DEFERRED_MAX_RETRIES):
        result = await provider.execute(task, worker)
        if result.status != WorkerStatus.DEFERRED:
            return result
        if attempt < _DEFERRED_MAX_RETRIES - 1:
            logger.warning(
                "run_tool_loop: %s deferred (no concurrency slot), retrying (%d/%d)",
                worker.id, attempt + 1, _DEFERRED_MAX_RETRIES,
            )
            await asyncio.sleep(_DEFERRED_BACKOFF_S)
    return result


async def run_tool_loop(
    task: WorkerTask,
    worker: WorkerManifest,
    provider: WorkerProviderBase,
    *,
    max_turns: int = _MAX_TOOL_TURNS,
    cwd: Path | None = None,
    delegation: DelegationContext | None = None,
    query_rewriter: Callable[[str, str | None], Awaitable[str]] | None = None,
) -> WorkerResult:
    """
    Drives provider.execute() through as many turns as needed to resolve
    every tool call the worker requests, up to max_turns total calls.

    Invariant: running_messages never contains a role:"system" entry --
    system framing + tool-list injection is rebuilt fresh every turn by
    the provider from task.context["system_prompt"], never baked into
    history. Baking it in would make OllamaProvider's inject_tools()
    re-append the "List of tools..." suffix onto an already-suffixed
    system message on every turn.

    *query_rewriter* (RESEARCH mode, SDD 5.1a.5): optional async callable
    ``(task_description, raw_query) -> rewritten_query`` applied to every
    ``web_search`` tool input before it is executed. Other tool calls and
    modes are unaffected.
    """
    cwd = cwd or Path.cwd()
    system_prompt = task.context.get("system_prompt")
    running_messages: list[dict] = list(task.context.get("messages") or [])
    if not running_messages:
        running_messages.append({"role": "user", "content": task.instruction})

    total_input_tok = 0
    total_output_tok = 0
    total_cost = 0.0
    total_duration_ms = 0
    accumulated_tool_results = []

    turn = 0
    prev_signature: tuple | None = None
    result: WorkerResult | None = None
    while True:
        turn += 1
        turn_task = dataclasses.replace(
            task,
            context={"messages": list(running_messages), "system_prompt": system_prompt},
        )
        result = await _execute_with_deferred_retry(provider, turn_task, worker)

        total_input_tok += result.usage.input_tokens
        total_output_tok += result.usage.output_tokens
        total_cost += result.usage.cost_usd
        total_duration_ms += result.duration_ms

        if result.status != WorkerStatus.SUCCESS:
            break
        if not result.tool_results:
            break

        # Non-termination guard (SDD 5.7a, task 8.3): a turn that requests
        # the identical tool-call set as the previous turn means the model
        # is ignoring its tool results and looping -- stop before executing
        # the duplicates or spending another (possibly Ollama-Cloud-
        # budgeted) provider call. Only *consecutive* identical requests
        # trigger this; repeating a call later in the task is legitimate.
        turn_signature = tuple(
            (tr.tool_name, json.dumps(tr.tool_input, sort_keys=True, default=str))
            for tr in result.tool_results
        )
        if turn_signature == prev_signature:
            logger.warning(
                "run_tool_loop: %s requested the identical tool call(s) %s on "
                "two consecutive turns -- terminating early (turn %d/%d) to "
                "avoid a runaway loop. instruction=%r",
                worker.model_id,
                [tr.tool_name for tr in result.tool_results],
                turn, max_turns, task.instruction[:80],
            )
            break
        prev_signature = turn_signature

        if turn >= max_turns:
            logger.warning(
                "run_tool_loop: %s hit max_turns=%d with tool calls still pending -- "
                "returning last turn's result as-is. instruction=%r",
                worker.model_id, max_turns, task.instruction[:80],
            )
            break

        # RESEARCH mode query rewrite (SDD 5.1a.5): before any web_search
        # call reaches Brave, rewrite vague/conversational queries into
        # keyword-focused search-engine queries. This happens after the
        # non-termination guard has seen the raw signature so a model that
        # re-emits the identical raw query still gets caught; the rewritten
        # query is what is actually executed.
        if query_rewriter is not None:
            rewritten: list[WorkerToolResult] = []
            for tr in result.tool_results:
                if tr.tool_name == "web_search":
                    raw_query = tr.tool_input.get("query")
                    rewritten_query = await query_rewriter(task.instruction, raw_query)
                    rewritten.append(
                        dataclasses.replace(
                            tr, tool_input={**tr.tool_input, "query": rewritten_query},
                        )
                    )
                else:
                    rewritten.append(tr)
            result = dataclasses.replace(result, tool_results=rewritten)

        # Parallel execution (SDD 5.1a) -- a single turn requesting multiple
        # tool calls (e.g. two web_search/retrieve calls) runs them
        # concurrently rather than one at a time. execute_tool() never
        # raises (every failure becomes .error on the result), so gather()
        # can't fail here even if one call does.
        executed = list(await asyncio.gather(*(
            execute_tool(tr, worker=worker, cwd=cwd, delegation=delegation)
            for tr in result.tool_results
        )))
        accumulated_tool_results.extend(executed)
        total_duration_ms += sum(tr.duration_ms for tr in executed)

        running_messages.append(
            result.raw_assistant_message
            or {"role": "assistant", "content": result.output or ""}
        )
        for i, tr in enumerate(executed):
            content = tr.tool_output if tr.error is None else f"ERROR: {tr.error}"
            tool_call_id = f"call_{i}" if worker.tool_protocol == ToolProtocol.NATIVE else None
            running_messages.append(
                format_tool_result_message(
                    tool_name=tr.tool_name,
                    result=content if content is not None else "",
                    role=worker.tool_result_role,
                    tool_call_id=tool_call_id,
                )
            )

    return dataclasses.replace(
        result,
        tool_results=accumulated_tool_results + (result.tool_results or []),
        usage=ModelUsage(total_input_tok, total_output_tok, total_cost),
        duration_ms=total_duration_ms,
    )
