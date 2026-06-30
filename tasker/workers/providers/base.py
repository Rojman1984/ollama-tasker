"""
tasker.workers.providers.base
-----------------------------
WorkerProviderBase ABC.
See SDD Section 7.2.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

# TODO Phase 4
#
# class WorkerProviderBase(ABC):
#     @abstractmethod
#     async def execute(self, task, worker) -> WorkerResult: ...
#     @abstractmethod
#     async def health_check(self, worker) -> bool: ...
#     @abstractmethod
#     def supports(self, worker) -> bool: ...