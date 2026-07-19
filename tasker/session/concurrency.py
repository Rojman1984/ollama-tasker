"""
tasker.session.concurrency
---------------------------
OllamaCloudConcurrencyManager — non-blocking slot manager for Ollama Cloud.

Plan limits: Free=1, Pro=3, Max=10.
try_acquire() returns True/False immediately — NEVER blocks the caller.
See SDD Section 5.9.
"""
from __future__ import annotations

import asyncio
import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from tasker.workers.base import OllamaPlan

logger = logging.getLogger(__name__)


_PLAN_SLOTS: dict[OllamaPlan, int] = {
    OllamaPlan.FREE: 1,
    OllamaPlan.PRO:  3,
    OllamaPlan.MAX:  10,
}


class OllamaCloudConcurrencyManager:
    """
    Tracks in-flight Ollama Cloud requests against the plan's concurrency limit.

    Usage::

        mgr = OllamaCloudConcurrencyManager(OllamaPlan.PRO)

        acquired = await mgr.try_acquire()
        if not acquired:
            return WorkerResult(status=WorkerStatus.DEFERRED, ...)
        try:
            result = await call_ollama_cloud(...)
        finally:
            await mgr.release()

    Or via context manager::

        async with mgr.slot() as acquired:
            if not acquired:
                return WorkerResult(status=WorkerStatus.DEFERRED, ...)
            result = await call_ollama_cloud(...)
    """

    def __init__(self, plan: OllamaPlan) -> None:
        self.plan = plan
        self.max_slots = _PLAN_SLOTS[plan]
        self._in_use = 0
        self._lock = asyncio.Lock()

    async def try_acquire(self) -> bool:
        """Non-blocking slot acquisition. Returns True if acquired, False if full."""
        async with self._lock:
            if self._in_use < self.max_slots:
                self._in_use += 1
                logger.info(
                    "OllamaCloud slot acquired (%d/%d in use, plan=%s)",
                    self._in_use, self.max_slots, self.plan.value,
                )
                return True
            logger.info(
                "OllamaCloud slot DENIED — all %d slot(s) in use (plan=%s)",
                self.max_slots, self.plan.value,
            )
            return False

    async def release(self) -> None:
        """Release a previously acquired slot."""
        async with self._lock:
            if self._in_use > 0:
                self._in_use -= 1
                logger.info(
                    "OllamaCloud slot released (%d/%d in use, plan=%s)",
                    self._in_use, self.max_slots, self.plan.value,
                )

    @property
    def slots_available(self) -> int:
        return max(0, self.max_slots - self._in_use)

    @property
    def is_full(self) -> bool:
        return self._in_use >= self.max_slots

    @asynccontextmanager
    async def slot(self) -> AsyncGenerator[bool, None]:
        """
        Async context manager. Yields True if a slot was acquired, False if full.
        Only releases on exit if the slot was actually acquired.
        """
        acquired = await self.try_acquire()
        try:
            yield acquired
        finally:
            if acquired:
                await self.release()
