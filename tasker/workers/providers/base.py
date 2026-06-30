"""
tasker.workers.providers.base
-----------------------------
WorkerProviderBase ABC.
See SDD Section 7.2.
"""
from __future__ import annotations

from abc import ABC, abstractmethod

from tasker.workers.base import WorkerManifest, WorkerResult, WorkerTask


class WorkerProviderBase(ABC):

    @abstractmethod
    async def execute(
        self,
        task: WorkerTask,
        worker: WorkerManifest,
    ) -> WorkerResult:
        """Execute a task on the specified worker. Returns result or status."""

    @abstractmethod
    async def health_check(
        self,
        worker: WorkerManifest,
    ) -> bool:
        """Return True if the worker is reachable and ready."""

    @abstractmethod
    def supports(
        self,
        worker: WorkerManifest,
    ) -> bool:
        """Return True if this provider can handle the given manifest."""
