"""
tasker.tools.honesty
---------------------
Side-effect honesty guard for worker results (SDD 5.7b).

Live bug: a cowork task asked for a file to be created; the worker's
final answer claimed "verified at example.txt" but the step executed
zero tool calls, so no file was ever written -- and the run synthesized
that claim as a normal success with nothing to indicate it was
unverified. This module flags exactly that shape (a side-effect claim in
the output text with no tool_results backing it) so the dispatch loop
can surface it honestly instead of passing it through to synthesis.
"""
from __future__ import annotations

import re

from tasker.workers.base import WorkerResult

# Dual-signal heuristic: a verb implying a side effect happened, combined
# with an object it happened to (or a filename-shaped token). Requiring
# both keeps ordinary chat answers ("I successfully explained the
# concept") from tripping the guard -- "successfully" alone is far too
# generic, but "successfully" + "file"/"command" rarely appears unless a
# real side-effect claim is being made.
_SIDE_EFFECT_VERBS = frozenset({
    "created", "creates", "wrote", "written", "writes", "saved", "saves",
    "executed", "executes", "ran", "run", "committed", "commits",
    "deleted", "deletes", "modified", "modifies", "updated", "updates",
    "verified", "verifies", "generated", "generates",
})
_SIDE_EFFECT_OBJECTS = frozenset({
    "file", "files", "path", "directory", "folder", "command", "script",
})
_FILENAME_RE = re.compile(r"\b[\w][\w\-]*\.[A-Za-z0-9]{1,6}\b")

UNVERIFIED_PREFIX = "[unverified] worker claimed side effects but used no tools."


def _claims_side_effect(output: str) -> bool:
    if not output:
        return False
    words = set(re.findall(r"[a-z]+", output.lower()))
    has_verb = bool(words & _SIDE_EFFECT_VERBS)
    has_object = bool(words & _SIDE_EFFECT_OBJECTS) or bool(_FILENAME_RE.search(output))
    return has_verb and has_object


def check_side_effect_honesty(result: WorkerResult) -> WorkerResult:
    """
    If *result* claims a side effect in its output text but its
    tool_results is empty (no tool was actually invoked this step),
    rewrite the output to lead with an explicit [unverified] marker
    carrying the original claim, so synthesis never presents an
    unverified claim as a plain success. Mutates and returns *result*;
    a result with no such claim, or one backed by at least one tool
    call, is returned unchanged.
    """
    if result.tool_results:
        return result
    if not _claims_side_effect(result.output or ""):
        return result

    original = result.output
    result.output = f"{UNVERIFIED_PREFIX} Original claim: {original}"
    return result
