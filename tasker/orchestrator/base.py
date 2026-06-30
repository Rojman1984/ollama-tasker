"""
tasker.orchestrator.base
-------------------------
OrchestratorBase ABC -- plan(), synthesize(), should_retry().

RULE: The orchestrator NEVER calls tools directly.
      It plans and synthesizes only. Workers execute.
See SDD Section 7.1.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from tasker.workers.base import (
    ClassifierResult,
    ExecutionPlan,
    RetryDecision,
    WorkerManifest,
    WorkerResult,
)


class OrchestratorBase(ABC):

    @abstractmethod
    async def plan(
        self,
        task: str,
        classifier_output: ClassifierResult,
        available_workers: list[WorkerManifest],
    ) -> ExecutionPlan:
        """Decompose task into ordered steps with role assignments."""

    @abstractmethod
    async def synthesize(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> str:
        """Merge worker outputs into a final response."""

    @abstractmethod
    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        """Decide: retry same worker, reassign to different worker, or fail."""
