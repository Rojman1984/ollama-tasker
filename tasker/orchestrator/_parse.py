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
        f"Step {i + 1}: {r.output or '(no output)'}"
        for i, r in enumerate(results)
    )
    return f"Original task: {original_task}\n\nWorker outputs:\n{outputs}"


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

def parse_plan(task: str, raw: str) -> ExecutionPlan | None:
    """Parse a model's JSON plan response into an ExecutionPlan. Returns None on error."""
    try:
        data = json.loads(raw.strip())
        if not isinstance(data, list) or not data:
            return None
        steps = []
        for i, item in enumerate(data):
            caps = {Capability(c) for c in item.get("capabilities", ["tool_use"])}
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
        )
    except (json.JSONDecodeError, KeyError, ValueError):
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
