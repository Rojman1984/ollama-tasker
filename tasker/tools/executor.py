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
import re
import shlex
import time
from pathlib import Path

from tasker.workers.base import ComputeLocation, ToolID, WorkerManifest, WorkerToolResult

_MAX_OUTPUT_CHARS = 8_000
_DEFAULT_TIMEOUT_S = 30.0
_TRUNCATION_MARKER = "\n... [output truncated]"

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
) -> WorkerToolResult:
    """
    Runs tool_result.tool_name for real and returns a NEW WorkerToolResult
    with tool_output/error/duration_ms populated. Never raises -- every
    failure mode (bad input, timeout, denied, unimplemented) becomes
    .error on the returned result so the multi-turn loop can feed it
    back to the model instead of crashing the step.
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


_DISPATCH = {
    ToolID.BASH.value: _exec_bash,
    ToolID.GIT.value: _exec_git,
    ToolID.FILE_READ.value: _exec_file_read,
    ToolID.FILE_WRITE.value: _exec_file_write,
    ToolID.CODE_SEARCH.value: _exec_code_search,
}
