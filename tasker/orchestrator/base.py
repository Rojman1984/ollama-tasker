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

# TODO Phase 3
#
# class OrchestratorBase(ABC):
#     @abstractmethod
#     async def plan(self, task, classifier_output, available_workers) -> ExecutionPlan: ...
#     @abstractmethod
#     async def synthesize(self, original_task, results) -> str: ...
#     @abstractmethod
#     async def should_retry(self, plan, failed_step) -> RetryDecision: ...