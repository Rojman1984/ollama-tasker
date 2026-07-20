"""
tasker.tools.bundles
---------------------
Tool bundle definitions per mode.

CHAT:     search, calculator, memory_read
CODE:     bash, file_read, file_write, git, linter, test_runner, code_search
COWORK:   ALL of CODE + checkpoint_write, task_state, progress_report,
          web_search, retrieve, mcp_call_tool, delegate_agent
RESEARCH: web_search, retrieve, pdf_extract, citation_tracker,
          contradiction_detector
SECURE:   file_read, file_write, local_search, local_memory (NO network tools)

See SDD Section 5.1.
"""
from __future__ import annotations

import logging

from tasker.workers.base import ToolDefinition, ToolID

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Network-capable tools — always stripped by SECURE mode
# --------------------------------------------------------------------------- #

NETWORK_TOOLS: frozenset[ToolID] = frozenset({
    ToolID.SEARCH,          # CHAT's web/knowledge search
    ToolID.WEB_SEARCH,
    ToolID.RETRIEVE,
    ToolID.MCP_CALL_TOOL,
    ToolID.DELEGATE_AGENT,
})

# --------------------------------------------------------------------------- #
# Canonical bundles (frozensets of ToolID)
# --------------------------------------------------------------------------- #

CHAT_BUNDLE: frozenset[ToolID] = frozenset({
    ToolID.SEARCH,
    ToolID.CALCULATOR,
    ToolID.MEMORY_READ,
})

CODE_BUNDLE: frozenset[ToolID] = frozenset({
    ToolID.BASH,
    ToolID.FILE_READ,
    ToolID.FILE_WRITE,
    ToolID.GIT,
    ToolID.LINTER,
    ToolID.TEST_RUNNER,
    ToolID.CODE_SEARCH,
})

COWORK_BUNDLE: frozenset[ToolID] = CODE_BUNDLE | frozenset({
    ToolID.CHECKPOINT_WRITE,
    ToolID.TASK_STATE,
    ToolID.PROGRESS_REPORT,
    ToolID.WEB_SEARCH,
    ToolID.RETRIEVE,
    ToolID.MCP_CALL_TOOL,
    ToolID.DELEGATE_AGENT,
})

RESEARCH_BUNDLE: frozenset[ToolID] = frozenset({
    ToolID.WEB_SEARCH,
    ToolID.RETRIEVE,
    ToolID.PDF_EXTRACT,
    ToolID.CITATION_TRACKER,
    ToolID.CONTRADICTION_DETECTOR,
})

SECURE_BUNDLE: frozenset[ToolID] = frozenset({
    ToolID.FILE_READ,
    ToolID.FILE_WRITE,
    ToolID.LOCAL_SEARCH,
    ToolID.LOCAL_MEMORY,
})

BUNDLES: dict[str, frozenset[ToolID]] = {
    "chat":     CHAT_BUNDLE,
    "code":     CODE_BUNDLE,
    "cowork":   COWORK_BUNDLE,
    "research": RESEARCH_BUNDLE,
    "secure":   SECURE_BUNDLE,
}

# --------------------------------------------------------------------------- #
# SECURE wrapping
# --------------------------------------------------------------------------- #

def secure_bundle(base_bundle: frozenset[ToolID]) -> frozenset[ToolID]:
    """
    Return the subset of *base_bundle* safe for SECURE mode.
    Strips all tools in NETWORK_TOOLS regardless of origin.
    """
    return base_bundle - NETWORK_TOOLS

# --------------------------------------------------------------------------- #
# Step-aware narrowing — offering a worker fewer, more relevant tools
# --------------------------------------------------------------------------- #
#
# Live testing found that offering a small local model (lfm2.5-thinking,
# 1.2B) the full 7-tool CODE_BUNDLE on every step reliably caused it to
# lose its answer inside its <think> block and never emit a parseable
# tool call -- reproduced identically across Q4, Q8, and full bf16
# precision, so this is a prompt-complexity problem, not a quantization
# one. Offering just the 1 tool a step actually needs was 100% reliable
# in every test. PlanStep only carries `description` (free text) and
# `required_capabilities` (too coarse -- e.g. Capability.CODE doesn't
# distinguish "run tests" from "read a file" from "git diff"), so
# narrowing is done deterministically via keyword matching on
# `description`, not by asking a model to classify (proven unreliable
# for this same reason).

# Each tool maps to a list of "groups" -- a group is a set of substrings
# that must ALL appear in the step description (any order/position) for
# that group to match; a tool matches if ANY of its groups match. Live
# testing found the planner paraphrases the same real intent multiple
# ways across runs (e.g. "List files in current directory" / "Listing
# files" / "List current directory files") -- a flat exact-phrase list
# missed the paraphrases, so word-co-occurrence groups (not just fixed
# phrases) are needed to keep up with that variance. Single-word groups
# behave like a plain "OR" keyword.
_TOOL_KEYWORDS: dict[ToolID, list[frozenset[str]]] = {
    # Broadest net: no dedicated directory-listing/general-command tool
    # exists, so "list files"/"hostname"-style steps must resolve here.
    # Deliberately NOT including bare "run "/"execute"/"command" -- too
    # generic, collides with "run tests"/"run git commit"-style steps.
    ToolID.BASH: [
        frozenset({"bash"}),
        frozenset({"shell"}),
        frozenset({"hostname"}),
        frozenset({"ls "}),
        frozenset({"list", "file"}),
        frozenset({"list", "director"}),
    ],
    ToolID.FILE_READ: [
        frozenset({"read", "file"}),
        frozenset({"open", "file"}),
        frozenset({"contents of"}),
        frozenset({"view", "file"}),
    ],
    ToolID.FILE_WRITE: [
        frozenset({"write", "file"}),
        frozenset({"write to"}),
        frozenset({"create", "file"}),
        frozenset({"save", "file"}),
        frozenset({"edit", "file"}),
    ],
    ToolID.GIT: [
        frozenset({"git "}),
        frozenset({"commit"}),
        frozenset({"diff"}),
        frozenset({"branch"}),
        frozenset({"clone"}),
        frozenset({"pull request"}),
    ],
    ToolID.LINTER: [
        frozenset({"lint"}),
        frozenset({"style check"}),
    ],
    ToolID.TEST_RUNNER: [
        frozenset({"test"}),
        frozenset({"pytest"}),
    ],
    ToolID.CODE_SEARCH: [
        frozenset({"search"}),
        frozenset({"find"}),
        frozenset({"grep"}),
        frozenset({"look for"}),
        frozenset({"locate"}),
    ],
    # RESEARCH mode grounding (SDD 5.1a): before this, no keyword group
    # existed for any of these -- narrow_bundle_to_step() always narrowed a
    # research step to an EMPTY tool set (CODE_SEARCH's "search"/"find"
    # keywords don't apply here; CODE_SEARCH isn't even in RESEARCH_BUNDLE),
    # so a research worker could never actually call web_search/retrieve
    # regardless of what the schema offered -- the root cause of a live
    # bug where research mode fabricated an entire model comparison and a
    # benchmark statistic with zero tool calls.
    ToolID.WEB_SEARCH: [
        frozenset({"search"}),
        frozenset({"research"}),
        frozenset({"find", "information"}),
        frozenset({"look up"}),
        frozenset({"web"}),
    ],
    ToolID.RETRIEVE: [
        frozenset({"retrieve"}),
        frozenset({"fetch"}),
        frozenset({"read", "url"}),
        frozenset({"read", "page"}),
        frozenset({"read", "source"}),
    ],
    ToolID.PDF_EXTRACT: [
        frozenset({"pdf"}),
        frozenset({"extract"}),
    ],
    ToolID.CITATION_TRACKER: [
        frozenset({"cite"}),
        frozenset({"citation"}),
        frozenset({"source"}),
    ],
    ToolID.CONTRADICTION_DETECTOR: [
        frozenset({"contradict"}),
        frozenset({"conflicting"}),
        frozenset({"verify", "claim"}),
    ],
    # DELEGATE_AGENT (SDD 5.7c) -- same lesson as WEB_SEARCH/RETRIEVE
    # (SDD 5.1a): no keyword group means narrow_bundle_to_step() can never
    # offer this tool no matter how real its executor is.
    ToolID.DELEGATE_AGENT: [
        frozenset({"delegate"}),
        frozenset({"sub-agent"}),
        frozenset({"subagent"}),
        frozenset({"spawn"}),
        frozenset({"assign", "to another"}),
    ],
}


def _match_keywords(bundle: frozenset[ToolID], text: str) -> frozenset[ToolID]:
    text = text.lower()
    return frozenset(
        tool_id for tool_id, groups in _TOOL_KEYWORDS.items()
        if any(all(word in text for word in group) for group in groups)
    ) & bundle


def narrow_bundle_to_step(
    bundle: frozenset[ToolID], step_description: str, original_task: str | None = None,
) -> frozenset[ToolID]:
    """
    Return the subset of *bundle* relevant to *step_description*, matched
    via _TOOL_KEYWORDS. If nothing matches and *original_task* is given,
    retry against the original user request -- the planner-generated
    step_description can be garbled or vague (e.g. "Listing available
    workers" for a step that should say "list files in the current
    directory", observed live on Designlab1 for exactly this task) even
    when the user's own original wording carries a clear keyword signal.
    If nothing matches either, returns an EMPTY set (not the full bundle)
    and logs a WARNING -- unmatched phrasing should stay visible/
    improvable, but live-verified evidence (Designlab1, this machine,
    lfm2.5-thinking:latest) shows falling back to the full bundle is
    actively harmful, not just imprecise: offered CHAT's 3-tool bundle for
    a plain "say hello in exactly five words" prompt with no relevant
    tool, the model hallucinated a plausible-looking but nonsensical call
    (`calculator(expression="hello")`) rather than answering directly,
    then failed to conclude across repeated turns once fed the resulting
    error -- exhausting run_tool_loop's max_turns. A step with no keyword
    match anywhere is, by definition, one this narrowing has no signal
    for; offering nothing forces the model to just answer, which every
    precedent in this project shows it's reliable at, whereas offering
    irrelevant tools is not.
    """
    matched = _match_keywords(bundle, step_description)
    if not matched and original_task:
        matched = _match_keywords(bundle, original_task)
    if not matched:
        logger.warning(
            "narrow_bundle_to_step: no keyword match for step description "
            "%r%s -- offering no tools for this step (was: full %d-tool "
            "bundle, changed after live evidence of hallucinated tool "
            "calls on unmatched steps)",
            step_description,
            " or original task" if original_task else "",
            len(bundle),
        )
        return frozenset()
    return matched

# --------------------------------------------------------------------------- #
# ToolDefinition registry — minimal schemas for all known tools
# --------------------------------------------------------------------------- #

_STR  = {"type": "string"}
_OBJ  = {"type": "object"}

_TOOL_META: dict[ToolID, tuple[str, dict]] = {
    ToolID.SEARCH: (
        "Search the web or a knowledge base",
        {"type": "object", "properties": {"query": _STR}, "required": ["query"]},
    ),
    ToolID.CALCULATOR: (
        "Evaluate a mathematical expression",
        {"type": "object", "properties": {"expression": _STR}, "required": ["expression"]},
    ),
    ToolID.MEMORY_READ: (
        "Read a value from session or project memory",
        {"type": "object", "properties": {"key": _STR}},
    ),
    ToolID.BASH: (
        "Execute a shell command",
        {"type": "object", "properties": {"command": _STR}, "required": ["command"]},
    ),
    ToolID.FILE_READ: (
        "Read a file from the local filesystem",
        {"type": "object", "properties": {"path": _STR}, "required": ["path"]},
    ),
    ToolID.FILE_WRITE: (
        "Write content to a local file",
        {
            "type": "object",
            "properties": {"path": _STR, "content": _STR},
            "required": ["path", "content"],
        },
    ),
    ToolID.GIT: (
        "Run a git subcommand",
        {"type": "object", "properties": {"args": _STR}, "required": ["args"]},
    ),
    ToolID.LINTER: (
        "Lint source code at the given path",
        {"type": "object", "properties": {"path": _STR}},
    ),
    ToolID.TEST_RUNNER: (
        "Run the project's test suite",
        {"type": "object", "properties": {"path": _STR}},
    ),
    ToolID.CODE_SEARCH: (
        "Search source code with a regex pattern",
        {"type": "object", "properties": {"pattern": _STR}, "required": ["pattern"]},
    ),
    ToolID.CHECKPOINT_WRITE: (
        "Write a named session checkpoint",
        {"type": "object", "properties": {"label": _STR}},
    ),
    ToolID.TASK_STATE: (
        "Read or update long-horizon task state",
        {"type": "object", "properties": {"action": _STR}},
    ),
    ToolID.PROGRESS_REPORT: (
        "Emit a step-progress event to the orchestrator",
        {"type": "object", "properties": {"message": _STR}, "required": ["message"]},
    ),
    ToolID.WEB_SEARCH: (
        "Perform a live web search",
        {"type": "object", "properties": {"query": _STR}, "required": ["query"]},
    ),
    ToolID.RETRIEVE: (
        "Fetch and return the content of a URL",
        {"type": "object", "properties": {"url": _STR}, "required": ["url"]},
    ),
    ToolID.MCP_CALL_TOOL: (
        "Invoke a tool on a registered MCP server",
        {
            "type": "object",
            "properties": {
                "server": _STR,
                "tool": _STR,
                "args": _OBJ,
            },
            "required": ["server", "tool"],
        },
    ),
    ToolID.DELEGATE_AGENT: (
        "Delegate a sub-task to a specialised sub-agent",
        {"type": "object", "properties": {"task": _STR}, "required": ["task"]},
    ),
    ToolID.PDF_EXTRACT: (
        "Extract text content from a PDF file",
        {"type": "object", "properties": {"path": _STR}, "required": ["path"]},
    ),
    ToolID.CITATION_TRACKER: (
        "Record and index a source citation",
        {"type": "object", "properties": {"source": _STR}, "required": ["source"]},
    ),
    ToolID.CONTRADICTION_DETECTOR: (
        "Check whether two claims logically contradict each other",
        {
            "type": "object",
            "properties": {"a": _STR, "b": _STR},
            "required": ["a", "b"],
        },
    ),
    ToolID.LOCAL_SEARCH: (
        "Search the local filesystem for files or content",
        {"type": "object", "properties": {"pattern": _STR}, "required": ["pattern"]},
    ),
    ToolID.LOCAL_MEMORY: (
        "Read from the local persistent memory store",
        {"type": "object", "properties": {"key": _STR}},
    ),
}


def get_definitions(bundle: frozenset[ToolID]) -> list[ToolDefinition]:
    """Convert a bundle of ToolIDs to ToolDefinition instances, sorted by name."""
    return [
        ToolDefinition(
            name=tid.value,
            description=_TOOL_META[tid][0],
            parameters=_TOOL_META[tid][1],
        )
        for tid in sorted(bundle, key=lambda t: t.value)
    ]
