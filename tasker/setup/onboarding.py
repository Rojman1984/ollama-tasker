"""
tasker.setup.onboarding
------------------------
Dynamic /model onboarding (SDD_ADDENDUM_PHASE8.md B.5.5): typing an
unregistered `/model <tag>` that looks like a genuine Ollama model tag
(e.g. "llama3.2:3b") pulls it, probes it for tool-calling readiness, and
registers it -- so a REPL session can redirect to any model the user
already knows the tag for, not just what's pre-populated in
worker_registry.yaml.

Ollama server rules (CLAUDE.md, binding): NEVER shell out to the `ollama`
CLI -- it auto-spawns a server if it can't reach one. Pulling goes
through HTTP POST /api/pull on OLLAMA_BASE_URL, same convention as every
other Ollama interaction in this codebase (OllamaProvider,
ReadinessChecker).

Prompting is the caller's job (same convention as
tasker.setup.readiness) -- this module never calls input(); cli/shell.py
owns the confirmation UX and decides whether to proceed.
"""
from __future__ import annotations

import json
import logging
from collections.abc import Awaitable, Callable
from pathlib import Path

from tasker.setup.readiness import (
    ReadinessChecker,
    _DEFAULT_REGISTRY_PATH,
    write_manifest_to_registry,
)
from tasker.workers.base import WorkerManifest
from tasker.workers.registry import WorkerRegistry

logger = logging.getLogger(__name__)

# Callable injected for testing: (base_url, model_name, progress_cb) ->
# (http_status, last_ndjson_object). Mirrors readiness.py's _get_fn/_post_fn
# injection pattern.
_PullFn = Callable[[str, str, "Callable[[dict], None] | None"], Awaitable[tuple[int, dict]]]


def looks_like_model_tag(worker_id: str) -> bool:
    """
    Heuristic: does *worker_id* look like a genuine Ollama "name:tag"
    model reference rather than a typo of a registry worker id?

    Deliberately narrow (requires a colon with content on both sides) --
    registry ids in this project never contain a colon (see
    ReadinessChecker._suggest_id's "-local"/"-cloud" suffix convention),
    while every real Ollama tag does ("llama3.2:3b", "qwen3:1.7b",
    "nemotron-3-ultra:cloud"). A broader heuristic would treat an
    ordinary typo of a known id (e.g. "lfm2.5-locl") as a model tag and
    offer to download something that was never intended.
    """
    if not worker_id or " " in worker_id:
        return False
    name, sep, tag = worker_id.partition(":")
    return bool(sep) and bool(name) and bool(tag)


async def _default_pull_fn(
    base_url: str, model_name: str, progress_cb: Callable[[dict], None] | None,
) -> tuple[int, dict]:
    import aiohttp

    url = f"{base_url.rstrip('/')}/api/pull"
    last: dict = {}
    async with aiohttp.ClientSession() as session:
        async with session.post(
            url, json={"model": model_name}, timeout=aiohttp.ClientTimeout(total=None),
        ) as resp:
            async for raw_line in resp.content:
                line = raw_line.decode("utf-8", errors="replace").strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                last = obj
                if progress_cb is not None:
                    progress_cb(obj)
            return resp.status, last


async def pull_model(
    base_url: str,
    model_name: str,
    *,
    progress_cb: Callable[[dict], None] | None = None,
    _pull_fn: _PullFn | None = None,
) -> tuple[bool, str]:
    """
    Pull *model_name* via Ollama's streaming /api/pull -- never the
    `ollama` CLI. Returns (success, message). Ollama streams one JSON
    object per line ({"status": "pulling manifest"}, {"status":
    "downloading", "completed": N, "total": M}, ..., {"status":
    "success"}), or {"error": "..."} on failure; *progress_cb* (if given)
    is called with every parsed object as it arrives.
    """
    fn = _pull_fn or _default_pull_fn
    try:
        status, last = await fn(base_url, model_name, progress_cb)
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"

    if status != 200:
        return False, last.get("error") or f"HTTP {status} from {base_url}/api/pull"
    if last.get("error"):
        return False, last["error"]
    if last.get("status") != "success":
        return False, f"unexpected final pull status: {last.get('status')!r}"
    return True, "pull succeeded"


async def onboard_model(
    model_tag: str,
    registry: WorkerRegistry,
    base_url: str,
    registry_path: Path | None = None,
    *,
    progress_cb: Callable[[dict], None] | None = None,
    _checker: ReadinessChecker | None = None,
    _pull_fn: _PullFn | None = None,
) -> tuple[WorkerManifest | None, str]:
    """
    Full onboarding flow for a confirmed, unregistered model tag: pull,
    probe for tool-calling readiness, and register on success. The
    caller (cli/shell.py's /model handler) is responsible for confirming
    with the user *before* calling this -- this function performs the
    download unconditionally once invoked.

    Returns (manifest, message). manifest is None if the pull failed or
    the model failed the readiness probe (not tool-capable, or
    registration is refused per SDD's "no Capability.TOOL_USE, no
    registration" rule) -- message explains why in either case.
    """
    ok, reason = await pull_model(base_url, model_tag, progress_cb=progress_cb, _pull_fn=_pull_fn)
    if not ok:
        return None, f"Pull failed: {reason}"

    write_path = registry_path or _DEFAULT_REGISTRY_PATH
    checker = _checker or ReadinessChecker(base_url=base_url, registry_path=write_path)
    result = await checker.check(model_tag)
    if not result.supported or result.suggested_manifest is None:
        return None, (
            f"Model '{model_tag}' was pulled but failed the tool-calling "
            f"readiness probe -- not registered (Capability.TOOL_USE is "
            f"mandatory for any harness worker)."
        )

    manifest = result.suggested_manifest
    write_manifest_to_registry(manifest, write_path)
    registry.register(manifest)
    return manifest, (
        f"Registered '{manifest.id}' (protocol={result.recommended_protocol.value}, "
        f"context={manifest.context_window})."
    )
