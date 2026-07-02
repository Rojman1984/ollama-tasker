"""
tasker.orchestrator._parse
---------------------------
Shared JSON parsing utilities and system-prompt constants used by
Tier 1, 2, and 3 orchestrators.  Extracted so each tier can import
the same prompts and parsers without duplicating them.
See SDD Section 5.3.
"""
from __future__ import annotations

import json
import logging
import uuid

from tasker.workers.base import (
    AgentRole,
    Capability,
    ClassifierResult,
    ExecutionPlan,
    PlanStep,
    RetryDecision,
    StepStatus,
    WorkerManifest,
    WorkerResult,
)

logger = logging.getLogger(__name__)

# Near-miss capability strings caught in live end-to-end CLI testing (not
# speculative) -- models occasionally emit these instead of the exact
# Capability enum value. Silently normalized, no warning: this is expected
# tolerance, not an error condition. Keep small and evidence-based.
CAPABILITY_ALIASES: dict[str, Capability] = {
    "tool_execution": Capability.TOOL_USE,
    "code_execution": Capability.CODE,
    "search_web": Capability.SEARCH,
}

# --------------------------------------------------------------------------- #
# System prompts
# --------------------------------------------------------------------------- #

PLAN_SYSTEM = """\
You are an orchestrator. Decompose the user task into an ordered sequence of steps.
Respond ONLY with a JSON array. Each element must be an object with exactly these keys:
  "description": string — what this step does
  "role": "thinker" | "worker" | "verifier"
  "capabilities": array of strings from [tool_use, code, reasoning, search, vision, thinking, long_context, multi_agent]
No markdown, no explanation, pure JSON."""

SYNTHESIZE_SYSTEM = """\
You are a synthesizer. Given the original task and the outputs from each worker step,
produce a single, coherent, complete response. No preamble, no meta-commentary."""

RETRY_SYSTEM = """\
A worker step has failed. Decide whether to retry it.
Respond ONLY with JSON: {"should_retry": bool, "reassign": bool, "reason": string}
No markdown, no explanation."""


# --------------------------------------------------------------------------- #
# User-prompt builders
# --------------------------------------------------------------------------- #

def build_plan_prompt(
    task: str,
    classifier_output: ClassifierResult,
    available_workers: list[WorkerManifest],
) -> str:
    worker_ids = [w.id for w in available_workers]
    return (
        f"Task: {task}\n"
        f"Type: {classifier_output.task_type.value}\n"
        f"Complexity: {classifier_output.complexity_score:.2f}\n"
        f"Available workers: {worker_ids}"
    )


def build_synthesize_prompt(original_task: str, results: list[WorkerResult]) -> str:
    outputs = "\n\n".join(
        f"Step {i + 1}: {r.output or '(no output)'}" + _format_tool_results(r)
        for i, r in enumerate(results)
    )
    return f"Original task: {original_task}\n\nWorker outputs:\n{outputs}"


def _format_tool_results(result: WorkerResult) -> str:
    """
    Real tool output, appended after a step's prose so synthesis stays
    grounded even when that prose is itself empty (see the multi-turn
    tool loop, tasker/tools/loop.py) -- without this, a step whose model
    output was lost (e.g. inside a reasoning model's <think> block) would
    still show real tool output as "(no output)" to the synthesizer.
    """
    executed = [tr for tr in result.tool_results if tr.tool_output is not None]
    if not executed:
        return ""
    lines = "".join(f"\n  [tool: {tr.tool_name}] -> {tr.tool_output}" for tr in executed)
    return lines


def build_retry_prompt(plan: ExecutionPlan, failed_step: WorkerResult) -> str:
    return (
        f"Task: {plan.original_task}\n"
        f"Failed step worker: {failed_step.worker_id}\n"
        f"Failure reason: {failed_step.reason or 'unknown'}\n"
        f"Status: {failed_step.status.value}"
    )


# --------------------------------------------------------------------------- #
# Parsers
# --------------------------------------------------------------------------- #

def _resolve_step_capabilities(raw_caps, step_index: int, raw_response: str) -> set[Capability]:
    """
    Resolve a step's raw capability strings to Capability enum members.

    A string that fails to match the enum is first checked against
    CAPABILITY_ALIASES (silent normalization, no warning -- expected). If it
    matches neither, it is dropped from this step's set and a WARNING is
    logged with the bad string, the step index, and the raw model response --
    but the rest of the plan (including other steps' capabilities) is left
    untouched. If a step ends up with zero valid capabilities, the caller's
    unconditional `caps.add(Capability.TOOL_USE)` provides the default.
    """
    resolved: set[Capability] = set()
    for c in raw_caps:
        try:
            resolved.add(Capability(c))
            continue
        except ValueError:
            pass
        alias = CAPABILITY_ALIASES.get(c)
        if alias is not None:
            resolved.add(alias)
            continue
        logger.warning(
            "parse_plan: step %d has unrecognized capability %r -- dropping it "
            "from this step (plan otherwise preserved). Raw model response: %s",
            step_index, c, raw_response,
        )
    return resolved


def _split_duplicate_description_objects(pairs: list[tuple[str, object]]) -> dict | list[dict]:
    """
    object_pairs_hook for json.loads(): small local models occasionally
    cram multiple logical plan steps into a single JSON object by
    repeating the "description" key instead of using separate array
    elements -- observed live (Designlab1, lfm2.5-thinking:latest) on a
    4-intent "create, verify, read, confirm" task collapsed into 2 objects
    each with 2 "description" values. Plain json.loads() silently keeps
    only the LAST value per duplicate key (per the JSON spec's
    implementation-defined handling), which corrupted the step's real,
    first-mentioned intent ("Create 'hello.txt'...") into its second,
    unrelated one ("Verify file existence...") with no error or warning --
    the worker then acted on the wrong instruction and never wrote the file.

    Splits an object into multiple objects whenever "description" repeats:
    each repeat starts a new object, and every other key (role,
    capabilities -- never observed duplicated) is carried forward into
    every split-out object via setdefault, since the model only stated
    those once for what it intended as several steps. Returns a plain
    dict when no duplicate "description" was found (the common case,
    behavior unchanged); returns a list of dicts when a split occurred --
    parse_plan() flattens these back into the top-level steps array.
    """
    _SPLIT_KEY = "description"
    seen_split_key = False
    groups: list[dict] = [{}]
    for key, value in pairs:
        if key == _SPLIT_KEY and seen_split_key:
            groups.append({})
        if key == _SPLIT_KEY:
            seen_split_key = True
        groups[-1][key] = value
    if len(groups) == 1:
        return groups[0]
    shared: dict = {}
    for g in groups:
        for k, v in g.items():
            if k != _SPLIT_KEY:
                shared[k] = v
    for g in groups:
        for k, v in shared.items():
            g.setdefault(k, v)
    return groups


def parse_plan(task: str, raw: str) -> ExecutionPlan | None:
    """
    Parse a model's JSON plan response into an ExecutionPlan. Returns None
    only when the response fails to parse as a valid plan structure at all
    (not valid JSON, not a list, empty, or missing required keys) -- that is
    the sole case that should trigger a caller's fallback to NanoOrchestrator.
    An unrecognized capability string inside an otherwise-valid step is
    handled per-step by _resolve_step_capabilities and never discards the
    rest of the plan. A step object with a duplicated "description" key is
    split into multiple steps by _split_duplicate_description_objects
    rather than silently losing its first-mentioned intent.
    """
    try:
        data = json.loads(raw.strip(), object_pairs_hook=_split_duplicate_description_objects)
        if not isinstance(data, list) or not data:
            return None
        flat_items: list[dict] = []
        for item in data:
            if isinstance(item, list):
                flat_items.extend(item)
            else:
                flat_items.append(item)
        steps = []
        for i, item in enumerate(flat_items):
            raw_caps = item.get("capabilities", ["tool_use"])
            caps = _resolve_step_capabilities(raw_caps, i, raw)
            caps.add(Capability.TOOL_USE)
            steps.append(
                PlanStep(
                    index=i,
                    description=str(item["description"]),
                    role=AgentRole(item.get("role", "worker")),
                    required_capabilities=caps,
                    depends_on=list(range(i)),
                    status=StepStatus.PENDING,
                )
            )
        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_task=task,
            steps=steps,
            dependency_graph={s.index: s.depends_on for s in steps},
            used_fallback=False,
        )
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        logger.warning(
            "parse_plan: response failed to parse as a valid plan structure; "
            "falling back to NanoOrchestrator template. Raw response: %s",
            raw,
        )
        return None


def parse_retry(raw: str) -> RetryDecision | None:
    try:
        data = json.loads(raw.strip())
        return RetryDecision(
            should_retry=bool(data["should_retry"]),
            reassign=bool(data["reassign"]),
            reason=str(data.get("reason", "")),
        )
    except (json.JSONDecodeError, KeyError):
        return None
