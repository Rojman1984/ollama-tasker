"""
tasker.tools.query_rewrite
---------------------------
RESEARCH mode search-query rewrite step (SDD 5.1a, point 5).

Before a `web_search` tool call is dispatched to the Brave Search API,
take the natural-language research task/step description (and the model's
draft query, if any) and rewrite them into a concise, keyword-focused search-
engine query. Uses the same ``(system_prompt, user_prompt) -> str``
model-call pattern as the orchestrator tiers
(`tasker.orchestrator.factory.make_call_model`) so it composes with any
provider already wired into the pipeline.

If the rewrite call fails or returns empty, the original draft query is
used so the search never blocks on the rewriter.
"""
from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable

from tasker.orchestrator.factory import make_call_model
from tasker.workers.base import ComputeLocation, PrivacyTier, WorkerManifest
from tasker.workers.providers.base import WorkerProviderBase

logger = logging.getLogger(__name__)

_REWRITE_SYSTEM = """\
You are a search-query specialist. Rewrite the research task description into \
a concise, effective web search query. Use specific keywords a search engine \
would match. Respond with ONLY the query string -- no markdown, no explanation, \
no surrounding quotes."""

_QueryRewriter = Callable[[str, str | None], Awaitable[str]]
_ModelCall = Callable[[str, str], Awaitable[str]]


def _build_rewrite_prompt(task_description: str, raw_query: str | None) -> str:
    prompt = f"Research task/step:\n{task_description}\n"
    if raw_query and raw_query.strip():
        prompt += f"\nModel's draft query:\n{raw_query}\n"
    prompt += "\nRewrite this into one effective web search query:"
    return prompt


async def rewrite_search_query(
    task_description: str,
    raw_query: str | None,
    call_model: _ModelCall,
) -> str:
    """
    Rewrite *task_description* (and the model's optional draft *raw_query*)
    into an effective Brave Search query using *call_model*.

    *call_model* follows the orchestrator convention:
    ``(system_prompt: str, user_prompt: str) -> str``.

    On any failure (empty response, exception) the original *raw_query* is
    returned so the search still proceeds. If *raw_query* is also empty, the
    original *task_description* is used as a last-resort fallback.
    """
    fallback = raw_query or task_description
    user_prompt = _build_rewrite_prompt(task_description, raw_query)
    try:
        rewritten = await call_model(_REWRITE_SYSTEM, user_prompt)
    except Exception as exc:
        logger.warning(
            "rewrite_search_query failed for %r: %s -- falling back to %r",
            task_description, exc, fallback,
        )
        return fallback

    rewritten = (rewritten or "").strip()
    # Strip a single pair of surrounding quotes if the model wrapped the
    # query in them, but preserve quotes that are part of the query itself.
    if len(rewritten) >= 2 and rewritten[0] == rewritten[-1] == '"':
        rewritten = rewritten[1:-1]
    if not rewritten:
        return fallback
    return rewritten


def build_query_rewriter(
    provider: WorkerProviderBase,
    worker: WorkerManifest,
) -> _QueryRewriter:
    """
    Build a query rewriter bound to *provider* and *worker*.

    The rewriter reuses the same worker manifest the step is already using,
    so no extra model load is incurred on sequential-load hardware. A short
    timeout is used because query rewriting is a small, fast prompt. Privacy
    tier is derived from the worker's compute_location so cloud-routed workers
    do not hit the LOCAL_ONLY hard block.
    """
    privacy_tier = (
        PrivacyTier.OLLAMA_CLOUD_OK
        if worker.compute_location == ComputeLocation.OLLAMA_CLOUD
        else PrivacyTier.LOCAL_ONLY
    )
    call_model = make_call_model(
        provider, worker, privacy_tier=privacy_tier, timeout_s=30.0,
    )

    async def rewriter(task_description: str, raw_query: str | None) -> str:
        return await rewrite_search_query(task_description, raw_query, call_model)

    return rewriter
