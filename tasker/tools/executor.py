"""
tasker.tools.executor
----------------------
Executes tool calls requested by worker LLMs, for real. Nothing in
core/ (despite being described elsewhere as "adopted from Parity
Project, do not rewrite") provides this -- core/bash_security.py and
its siblings are 6-line stubs with no implementation, confirmed while
investigating the multi-turn tool loop this module supports. See
docs/SDD.md's multi-turn tool loop section for the full security
posture rationale.

Security posture (see docs/SDD.md for the full writeup): this targets a
local, single-user dev CLI, but COWORK_BUNDLE pairs `bash` with
network tools under privacy_tier=any_cloud, so a cloud-routed worker
could otherwise be tricked into driving local execution. Two
enforcement points live here:
  - BASH/FILE_WRITE/GIT are hard-gated to LOCAL_HARDWARE workers,
    regardless of what a mode's privacy_tier allowed at planning time.
  - A small BASH denylist blocks a handful of obviously catastrophic
    command shapes. This is a speed bump, not a sandbox -- real safety
    rests on the LOCAL_HARDWARE gate and the user's own trust in their
    local model/machine.
LINTER and TEST_RUNNER are deliberately not implemented: no linter or
test framework is configured anywhere in this project, so guessing
which one to invoke would be worse than a clear error.
"""
from __future__ import annotations

import asyncio
import dataclasses
import os
import re
import shlex
import time
import urllib.parse
from pathlib import Path

from tasker.runtime.delegation import DelegationContext
from tasker.workers.base import ComputeLocation, ToolID, WorkerManifest, WorkerToolResult

_MAX_OUTPUT_CHARS = 8_000
_DEFAULT_TIMEOUT_S = 30.0
_TRUNCATION_MARKER = "\n... [output truncated]"

# RESEARCH mode grounding (SDD 5.1a): WEB_SEARCH via the Brave Search API,
# RETRIEVE via a direct HTTP fetch + HTML-to-text strip. Both are real
# network tool executors -- see docs/SDD.md 5.1a for the full grounding
# contract these feed into (narrow_bundle_to_step must also offer these
# tools for a research step to ever call them; see tasker/tools/bundles.py's
# _TOOL_KEYWORDS).
_BRAVE_SEARCH_URL = "https://api.search.brave.com/res/v1/web/search"
_MAX_SEARCH_RESULTS = 5
_NO_SEARCH_BACKEND_ERROR = (
    "no search backend configured -- set BRAVE_API_KEY to enable web_search"
)

_LOCAL_ONLY_TOOLS = {ToolID.BASH.value, ToolID.FILE_WRITE.value, ToolID.GIT.value}

# Defense-in-depth only, not a security boundary -- see module docstring.
_BASH_DENYLIST_PATTERNS = [
    re.compile(p, re.IGNORECASE)
    for p in [
        r"\brm\s+-rf\b",
        r"\bsudo\b",
        r"\bmkfs\b",
        r"\bdd\s+if=",
        r":\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:",  # fork bomb
        r"\b(curl|wget)\b.*\|\s*(sh|bash)\b",
        r">\s*/dev/sd",
        r"\bchmod\s+-R\s+777\s+/",
    ]
]


def _truncate(text: str) -> str:
    if len(text) <= _MAX_OUTPUT_CHARS:
        return text
    return text[:_MAX_OUTPUT_CHARS] + _TRUNCATION_MARKER


def _contain_path(raw_path: str, cwd: Path) -> Path:
    """Resolve raw_path under cwd, raising ValueError if it escapes."""
    candidate = (cwd / raw_path).resolve()
    cwd_resolved = cwd.resolve()
    if candidate != cwd_resolved and cwd_resolved not in candidate.parents:
        raise ValueError(f"path {raw_path!r} escapes the working directory")
    return candidate


async def execute_tool(
    tool_result: WorkerToolResult,
    *,
    worker: WorkerManifest,
    cwd: Path,
    timeout_s: float = _DEFAULT_TIMEOUT_S,
    delegation: DelegationContext | None = None,
) -> WorkerToolResult:
    """
    Runs tool_result.tool_name for real and returns a NEW WorkerToolResult
    with tool_output/error/duration_ms populated. Never raises -- every
    failure mode (bad input, timeout, denied, unimplemented) becomes
    .error on the returned result so the multi-turn loop can feed it
    back to the model instead of crashing the step.

    *delegation* (SDD 5.7c) is only consulted for DELEGATE_AGENT -- every
    other tool ignores it. None (the default) means "delegation isn't
    wired into this call site", which DELEGATE_AGENT reports as its own
    clean error rather than crashing.
    """
    start = time.monotonic()
    try:
        if (
            tool_result.tool_name in _LOCAL_ONLY_TOOLS
            and worker.compute_location != ComputeLocation.LOCAL_HARDWARE
        ):
            return dataclasses.replace(
                tool_result,
                error=(
                    f"Tool '{tool_result.tool_name}' is restricted to LOCAL_HARDWARE "
                    f"workers (this worker is {worker.compute_location.value})"
                ),
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        if tool_result.tool_name == ToolID.DELEGATE_AGENT.value:
            output, error = await _exec_delegate_agent(tool_result.tool_input, delegation)
            return dataclasses.replace(
                tool_result,
                tool_output=output,
                error=error,
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        handler = _DISPATCH.get(tool_result.tool_name)
        if handler is None:
            return dataclasses.replace(
                tool_result,
                error=f"no execution implementation configured for tool '{tool_result.tool_name}'",
                duration_ms=int((time.monotonic() - start) * 1000),
            )

        output, error = await handler(tool_result.tool_input, cwd, timeout_s)
        return dataclasses.replace(
            tool_result,
            tool_output=output,
            error=error,
            duration_ms=int((time.monotonic() - start) * 1000),
        )
    except Exception as exc:
        return dataclasses.replace(
            tool_result,
            error=f"{type(exc).__name__}: {exc}",
            duration_ms=int((time.monotonic() - start) * 1000),
        )


async def _run_argv(argv: list[str], cwd: Path, timeout_s: float) -> tuple[str | None, str | None]:
    try:
        proc = await asyncio.create_subprocess_exec(
            *argv,
            cwd=cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return None, f"{argv[0]}: not found ({exc})"

    try:
        stdout, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout_s)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return None, f"timed out after {timeout_s}s"

    out_text = stdout.decode("utf-8", errors="replace")
    err_text = stderr.decode("utf-8", errors="replace")
    if err_text:
        combined = f"{out_text}\n[stderr]\n{err_text}" if out_text else f"[stderr]\n{err_text}"
    else:
        combined = out_text
    combined = _truncate(combined)
    if proc.returncode != 0:
        return combined, f"exited with code {proc.returncode}"
    return combined, None


async def _exec_bash(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[str | None, str | None]:
    command = tool_input.get("command")
    if not command:
        return None, "missing required 'command'"
    for pattern in _BASH_DENYLIST_PATTERNS:
        if pattern.search(command):
            return None, f"command blocked by safety denylist: {command!r}"
    return await _run_argv(["bash", "-c", command], cwd, timeout_s)


async def _exec_git(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[str | None, str | None]:
    args = tool_input.get("args")
    if not args:
        return None, "missing required 'args'"
    return await _run_argv(["git", *shlex.split(args)], cwd, timeout_s)


async def _exec_code_search(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[str | None, str | None]:
    pattern = tool_input.get("pattern")
    if not pattern:
        return None, "missing required 'pattern'"
    argv = [
        "grep", "-rnE",
        "--exclude-dir=.git", "--exclude-dir=__pycache__", "--exclude-dir=.venv",
        "--exclude-dir=node_modules", "--exclude-dir=dist", "--exclude-dir=build",
        "-e", pattern, ".",
    ]
    output, error = await _run_argv(argv, cwd, timeout_s)
    # grep exits 1 for "no matches" -- not a real error, just an empty result.
    if error == "exited with code 1":
        return "(no matches)", None
    return output, error


async def _exec_file_read(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[str | None, str | None]:
    raw_path = tool_input.get("path")
    if not raw_path:
        return None, "missing required 'path'"
    try:
        path = _contain_path(raw_path, cwd)
    except ValueError as exc:
        return None, str(exc)
    if not path.exists():
        return None, f"no such file: {raw_path}"
    try:
        content = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return None, f"'{raw_path}' is not a text file"
    except OSError as exc:
        return None, str(exc)
    return _truncate(content), None


async def _exec_file_write(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[str | None, str | None]:
    raw_path = tool_input.get("path")
    content = tool_input.get("content")
    if not raw_path or content is None:
        return None, "missing required 'path' and/or 'content'"
    try:
        path = _contain_path(raw_path, cwd)
    except ValueError as exc:
        return None, str(exc)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    except OSError as exc:
        return None, str(exc)
    return f"wrote {len(content)} bytes to {raw_path}", None


# --------------------------------------------------------------------------- #
# DELEGATE_AGENT -- sub-task dispatch (SDD 5.7c)
# --------------------------------------------------------------------------- #

async def _exec_delegate_agent(
    tool_input: dict, delegation: DelegationContext | None,
) -> tuple[dict | None, str | None]:
    """
    Spawn a sub-task through the SAME dispatch pipeline the parent task is
    using (tasker/runtime/dispatch.py's _run_task()) -- inherited mode,
    routing policy, and privacy tier (all baked into the shared
    ExecutionConfig the reused pipeline carries), the SAME shared budget
    and concurrency manager (a sub-agent consumes the parent's own Ollama
    Cloud slots/budget, never a separate allowance), bounded depth, and a
    per-top-level-task sub-agent cap (SDD 5.7c) -- never trusts the
    requesting model's own claims about how deep or how many.
    """
    task_text = tool_input.get("task")
    if not task_text:
        return None, "missing required 'task'"
    if delegation is None:
        return None, "delegate_agent is not available outside a dispatched task"
    if delegation.depth >= delegation.max_depth:
        return None, (
            f"delegation depth limit ({delegation.max_depth}) reached -- "
            f"cannot spawn a further sub-agent from here"
        )
    if delegation.spawned[0] >= delegation.max_sub_agents:
        return None, f"sub-agent cap ({delegation.max_sub_agents}) reached for this task"
    delegation.spawned[0] += 1

    # Deferred import: tasker.runtime.dispatch -> tasker.tools.loop ->
    # tasker.tools.executor already exists in the other direction: a
    # module-level import here would be a real cycle. Safe deferred --
    # both modules are fully loaded by the time any tool actually executes.
    from tasker.runtime.dispatch import _run_task

    child = delegation.child()
    print(f"  [sub-agent depth={child.depth}] delegating: {task_text[:70]}...")
    output = await _run_task(
        task_text, delegation.mode_name, delegation.registry, delegation.store,
        pipeline=delegation.pipeline, delegation=child,
    )
    if output is None:
        return None, "sub-agent task did not complete (see output above for details)"
    return {"task": task_text, "result": output}, None


# --------------------------------------------------------------------------- #
# WEB_SEARCH / RETRIEVE -- RESEARCH mode grounding (SDD 5.1a)
# --------------------------------------------------------------------------- #

async def _default_search_get(url: str, headers: dict, timeout_s: float) -> tuple[int, dict | str]:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(
            url, headers=headers, timeout=aiohttp.ClientTimeout(total=timeout_s),
        ) as resp:
            try:
                data = await resp.json(content_type=None)
            except Exception:
                data = await resp.text()
            return resp.status, data


async def _default_page_get(url: str, timeout_s: float) -> tuple[int, str]:
    import aiohttp
    async with aiohttp.ClientSession() as session:
        async with session.get(url, timeout=aiohttp.ClientTimeout(total=timeout_s)) as resp:
            text = await resp.text(errors="replace")
            return resp.status, text


# Swappable module-level defaults (mock.patch these two names directly in
# tests) -- executor.py has no class to hang constructor injection off of,
# unlike ReadinessChecker/OllamaProvider's _get_fn/_post_fn pattern.
_search_get_fn = _default_search_get
_page_get_fn = _default_page_get

_TAG_RE = re.compile(r"<[^>]+>")
_WHITESPACE_RE = re.compile(r"[ \t]+")
_HTML_ENTITIES = {
    "&nbsp;": " ", "&amp;": "&", "&lt;": "<", "&gt;": ">", "&quot;": '"', "&#39;": "'",
}


def _strip_html(html: str) -> str:
    """Best-effort HTML-to-text: drop script/style blocks, strip tags,
    unescape the handful of entities that show up in ordinary prose. Not a
    full HTML parser -- good enough to hand a research worker readable
    page text, not to preserve layout or handle malformed markup."""
    html = re.sub(r"(?is)<(script|style)\b.*?</\1>", " ", html)
    text = _TAG_RE.sub(" ", html)
    for entity, replacement in _HTML_ENTITIES.items():
        text = text.replace(entity, replacement)
    text = re.sub(r"\s*\n\s*", "\n", text)
    text = _WHITESPACE_RE.sub(" ", text)
    return text.strip()


async def _exec_web_search(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[dict | None, str | None]:
    query = tool_input.get("query")
    if not query:
        return None, "missing required 'query'"
    api_key = os.environ.get("BRAVE_API_KEY")
    if not api_key:
        return None, _NO_SEARCH_BACKEND_ERROR
    headers = {"Accept": "application/json", "X-Subscription-Token": api_key}
    url = f"{_BRAVE_SEARCH_URL}?q={urllib.parse.quote(query)}"
    try:
        status, data = await _search_get_fn(url, headers, timeout_s)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if status != 200:
        return None, f"Brave Search API returned HTTP {status}"
    if not isinstance(data, dict):
        return None, "unexpected response from Brave Search API"
    raw_results = (data.get("web") or {}).get("results") or []
    results = [
        {"title": r.get("title", ""), "url": r.get("url", ""), "snippet": r.get("description", "")}
        for r in raw_results[:_MAX_SEARCH_RESULTS]
        if r.get("url")
    ]
    return {"query": query, "results": results}, None


async def _exec_retrieve(tool_input: dict, cwd: Path, timeout_s: float) -> tuple[dict | None, str | None]:
    url = tool_input.get("url")
    if not url:
        return None, "missing required 'url'"
    if not url.startswith(("http://", "https://")):
        return None, f"'url' must be an absolute http(s) URL, got {url!r}"
    try:
        status, body = await _page_get_fn(url, timeout_s)
    except Exception as exc:
        return None, f"{type(exc).__name__}: {exc}"
    if status != 200:
        return None, f"HTTP {status} fetching {url}"
    content = _truncate(_strip_html(body))
    return {"url": url, "content": content}, None


_DISPATCH = {
    ToolID.BASH.value: _exec_bash,
    ToolID.GIT.value: _exec_git,
    ToolID.FILE_READ.value: _exec_file_read,
    ToolID.FILE_WRITE.value: _exec_file_write,
    ToolID.CODE_SEARCH.value: _exec_code_search,
    ToolID.WEB_SEARCH.value: _exec_web_search,
    ToolID.RETRIEVE.value: _exec_retrieve,
}
