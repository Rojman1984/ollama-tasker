"""
tasker.tools.honesty
---------------------
Honesty guards for worker/synthesis output: side-effect claims (SDD
5.7b) and RESEARCH mode grounding (SDD 5.1a).

Live bug 1: a cowork task asked for a file to be created; the worker's
final answer claimed "verified at example.txt" but the step executed
zero tool calls, so no file was ever written -- and the run synthesized
that claim as a normal success with nothing to indicate it was
unverified. This module flags exactly that shape (a side-effect claim in
the output text with no tool_results backing it) so the dispatch loop
can surface it honestly instead of passing it through to synthesis.

Live bug 2: a RESEARCH-mode task fabricated an entire model comparison
and a benchmark statistic with zero tool calls. check_research_grounding()
is the same "never silently pass through an unverifiable claim"
philosophy, applied to RESEARCH mode's factual output instead of side
effects.
"""
from __future__ import annotations

import re

from tasker.workers.base import WorkerResult, WorkerToolResult

# Dual-signal heuristic: a verb implying a side effect happened, combined
# with an object it happened to (or a filename-shaped token). Requiring
# both keeps ordinary chat answers ("I successfully explained the
# concept") from tripping the guard -- "successfully" alone is far too
# generic, but "successfully" + "file"/"command" rarely appears unless a
# real side-effect claim is being made.
_SIDE_EFFECT_VERBS = frozenset({
    "create", "created", "creates", "write", "wrote", "written", "writes",
    "save", "saved", "saves", "execute", "executed", "executes",
    "run", "ran", "commit", "committed", "commits", "delete", "deleted",
    "deletes", "modify", "modified", "modifies", "update", "updated",
    "updates", "verify", "verified", "verifies", "generate", "generated",
    "generates",
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


def check_side_effect_honesty(result: WorkerResult, *context_texts: str) -> WorkerResult:
    """
    If *result* claims a side effect in its output text but its
    tool_results is empty (no tool was actually invoked this step),
    rewrite the output to lead with an explicit [unverified] marker
    carrying the original claim, so synthesis never presents an
    unverified claim as a plain success. Mutates and returns *result*;
    a result with no such claim, or one backed by at least one tool
    call, is returned unchanged.

    *context_texts* -- typically the original task and/or the step
    description -- gate the guard: it only ever fires when at least one
    of them itself implies a side effect was requested. Live bug: gating
    on the model's OUTPUT text alone false-positived on a plain "Hello"
    greeting whose reply merely *mentioned* file/command language (e.g.
    an offer like "let me know if you'd like me to create a file")
    without claiming to have done anything -- nothing about the request
    itself asked for a side effect, so the guard should never have looked
    at the answer's wording in the first place. Passing no context_texts
    at all disables the guard entirely (safer default than firing blind).
    """
    if result.tool_results:
        return result
    if not any(_claims_side_effect(text) for text in context_texts if text):
        return result
    if not _claims_side_effect(result.output or ""):
        return result

    original = result.output
    result.output = f"{UNVERIFIED_PREFIX} Original claim: {original}"
    return result


# --------------------------------------------------------------------------- #
# RESEARCH mode grounding (SDD 5.1a)
# --------------------------------------------------------------------------- #

_RETRIEVAL_TOOL_NAMES = frozenset({"web_search", "retrieve"})

RESEARCH_UNVERIFIED_PREFIX = "[unverified -- no sources retrieved]"


def check_research_grounding(
    output: str | None, tool_results: list[WorkerToolResult],
) -> str | None:
    """
    RESEARCH mode's grounding honesty guard (SDD 5.1a): if *output* is
    non-empty and *tool_results* contains no web_search/retrieve call,
    prefix it with RESEARCH_UNVERIFIED_PREFIX so a factual-sounding
    answer with no real retrieval behind it is never presented as
    grounded fact. Unlike check_side_effect_honesty(), this has no
    output-side keyword gate -- ANY research output with zero retrieval
    calls is unverifiable by construction, regardless of its wording.

    Caller decides *when* this applies (only mode_name == "research");
    this function itself is mode-agnostic so it can be reused both per
    step (tasker/runtime/dispatch.py's _execute_steps) and against the
    final synthesized answer (aggregated tool_results across every step).
    """
    if not output:
        return output
    if any(tr.tool_name in _RETRIEVAL_TOOL_NAMES for tr in tool_results):
        return output
    if output.startswith(RESEARCH_UNVERIFIED_PREFIX):
        return output
    return f"{RESEARCH_UNVERIFIED_PREFIX} {output}"
