"""
tasker.orchestrator.base
-------------------------
OrchestratorBase ABC -- plan(), synthesize(), should_retry().

RULE: The orchestrator NEVER calls tools directly.
      It plans and synthesizes only. Workers execute.
See SDD Section 7.1.
"""
from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from tasker.workers.base import (
    ClassifierResult,
    ExecutionPlan,
    RetryDecision,
    WorkerManifest,
    WorkerResult,
)


def _sentence_chunks(text: str) -> list[str]:
    """Sentence-chunking fallback for synthesize_stream (SDD 7.5a)."""
    if not text:
        return [""] if text == "" else []
    chunks = [s.strip() for s in re.split(r"(?<=[.!?])(?=\s+|$)", text) if s.strip()]
    return chunks or [text]


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

    async def synthesize_stream(
        self,
        original_task: str,
        results: list[WorkerResult],
    ) -> AsyncIterator[str]:
        """
        Streaming variant of synthesize().

        Default implementation uses the documented sentence-chunking fallback
        (SDD 7.5a): call synthesize(), split on sentence boundaries, and yield
        each chunk. Concrete orchestrator tiers that have a real streaming
        model call should override this method to yield genuine token deltas.
        """
        text = await self.synthesize(original_task, results)
        for chunk in _sentence_chunks(text):
            yield chunk

    @abstractmethod
    async def should_retry(
        self,
        plan: ExecutionPlan,
        failed_step: WorkerResult,
    ) -> RetryDecision:
        """Decide: retry same worker, reassign to different worker, or fail."""
