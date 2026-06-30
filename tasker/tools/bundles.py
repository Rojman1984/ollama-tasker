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

from tasker.workers.base import ToolDefinition, ToolID

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
