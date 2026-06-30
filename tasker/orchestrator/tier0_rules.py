"""
tasker.orchestrator.tier0_rules
--------------------------------
NanoOrchestrator (Tier 0) -- rule-based, NO model required.
Always works on any hardware. Used on TASKER-P1 under pressure.
See SDD Section 5.3.
"""
from __future__ import annotations

import uuid

from tasker.orchestrator.base import OrchestratorBase
from tasker.workers.base import (
    AgentRole,
    Capability,
    ClassifierResult,
    ExecutionPlan,
    PlanStep,
    RetryDecision,
    StepStatus,
    TaskType,
    WorkerManifest,
    WorkerResult,
)


# Template: (description, role, required_capabilities)
_STEP = tuple[str, AgentRole, set[Capability]]

_TEMPLATES: dict[TaskType, list[_STEP]] = {
    TaskType.CONVERSATIONAL: [
        ("Answer the task", AgentRole.WORKER, {Capability.TOOL_USE}),
    ],
    TaskType.TOOL_EXECUTION: [
        ("Execute the required tool operations", AgentRole.WORKER, {Capability.TOOL_USE}),
    ],
    TaskType.CODING: [
        (
            "Analyze the coding task and plan the implementation",
            AgentRole.THINKER,
            {Capability.TOOL_USE, Capability.CODE},
        ),
        (
            "Implement the solution",
            AgentRole.WORKER,
            {Capability.TOOL_USE, Capability.CODE},
        ),
    ],
    TaskType.RESEARCH: [
        (
            "Search for relevant information",
            AgentRole.WORKER,
            {Capability.TOOL_USE, Capability.SEARCH},
        ),
        (
            "Analyze and synthesize findings",
            AgentRole.THINKER,
            {Capability.TOOL_USE, Capability.REASONING},
        ),
        (
            "Compile and format the final report",
            AgentRole.WORKER,
            {Capability.TOOL_USE},
        ),
    ],
    TaskType.REASONING: [
        (
            "Reason through the problem",
            AgentRole.THINKER,
            {Capability.TOOL_USE, Capability.REASONING},
        ),
        (
            "Formulate and deliver the answer",
            AgentRole.WORKER,
            {Capability.TOOL_USE},
        ),
    ],
}


class NanoOrchestrator(OrchestratorBase):
    """
    Tier 0: pure rule-based orchestrator.

    Makes zero model calls. Applies fixed step templates keyed by task_type
    from the ClassifierResult. Synthesizes by joining worker outputs with
    double newlines. Never retries.
    """

    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        template = _TEMPLATES.get(classifier_output.task_type, _TEMPLATES[TaskType.CONVERSATIONAL])
        steps = [
            PlanStep(
                index=i,
                description=desc,
                role=role,
                required_capabilities=caps,
                depends_on=list(range(i)),   # each step depends on all previous
                status=StepStatus.PENDING,
            )
            for i, (desc, role, caps) in enumerate(template)
        ]
        dependency_graph: dict[int, list[int]] = {s.index: s.depends_on for s in steps}
        return ExecutionPlan(
            plan_id=str(uuid.uuid4()),
            original_task=task,
            steps=steps,
            dependency_graph=dependency_graph,
        )

    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> str:
        parts = [r.output for r in results if r.output]
        if not parts:
            return ""
        return "\n\n".join(parts)

    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        return RetryDecision(
            should_retry=False,
            reassign=False,
            reason="NanoOrchestrator does not retry — no model to decide.",
        )
