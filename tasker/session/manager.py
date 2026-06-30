"""
tasker.session.manager
-----------------------
SessionManager -- full lifecycle state machine.

States: RUNNING -> THROTTLING -> PAUSING -> CHECKPOINTING -> PAUSED -> RESUMING
Called before every worker dispatch via tick().
See SDD Sections 5.8 and 9.
"""
from __future__ import annotations

import asyncio
import uuid
from datetime import datetime

from tasker.session.budget import OllamaSessionBudget
from tasker.session.checkpoint import Checkpoint, CheckpointStore
from tasker.session.notifier import NotifierBase, SessionEvent
from tasker.workers.base import SessionDirective, SessionState


class SessionManager:
    """
    Owns the session state machine.

    tick() is called (synchronously) before every worker dispatch and returns a
    SessionDirective. Pause/resume flows are async because they fire notifiers
    and may schedule timers.
    """

    def __init__(
        self,
        budget: OllamaSessionBudget,
        store: CheckpointStore,
        notifier: NotifierBase,
        *,
        auto_resume: bool = True,
    ) -> None:
        self._budget = budget
        self._store = store
        self._notifier = notifier
        self._auto_resume = auto_resume
        self._state = SessionState.RUNNING
        self._session_id = str(uuid.uuid4())
        self._pause_event = asyncio.Event()
        self._pause_event.set()   # un-blocked at start; clear() when paused
        self._resume_timer: asyncio.TimerHandle | None = None

    # ------------------------------------------------------------------ #
    # Public read properties
    # ------------------------------------------------------------------ #

    @property
    def state(self) -> SessionState:
        return self._state

    @property
    def budget(self) -> OllamaSessionBudget:
        return self._budget

    @property
    def session_id(self) -> str:
        return self._session_id

    # ------------------------------------------------------------------ #
    # Core tick (SDD 9.1)
    # ------------------------------------------------------------------ #

    def tick(self) -> SessionDirective:
        """
        Evaluate the current budget and return a directive to the orchestrator.
        Must be called before every worker dispatch.
        """
        if self._state == SessionState.PAUSED:
            return SessionDirective.HOLD

        if self._budget.is_exhausted:
            if self._state not in (SessionState.PAUSING, SessionState.CHECKPOINTING):
                self._state = SessionState.PAUSING
            return SessionDirective.PAUSE

        if self._budget.should_throttle:
            self._state = SessionState.THROTTLING
            return SessionDirective.CONTINUE_LOCAL_ONLY

        if self._state == SessionState.THROTTLING:
            self._state = SessionState.RUNNING

        return SessionDirective.CONTINUE

    # ------------------------------------------------------------------ #
    # Pause flow (SDD 9.2)
    # ------------------------------------------------------------------ #

    async def pause(self, checkpoint: Checkpoint) -> None:
        """
        Execute the full pause flow after the current step completes:
        PAUSING -> CHECKPOINTING: persist checkpoint, optionally schedule
        auto-resume timer, fire PauseNotification, transition to PAUSED.
        """
        self._state = SessionState.CHECKPOINTING
        self._store.save(checkpoint)

        resume_at = checkpoint.resume_at
        if self._auto_resume and resume_at is not None:
            wait_s = (resume_at - datetime.now().astimezone()).total_seconds()
            if wait_s > 0:
                loop = asyncio.get_event_loop()
                self._resume_timer = loop.call_later(
                    wait_s,
                    lambda: asyncio.ensure_future(self._trigger_auto_resume(checkpoint.id)),
                )

        await self._notifier.send(
            SessionEvent.paused(
                f"Session paused. Checkpoint: {checkpoint.id}",
                checkpoint_id=checkpoint.id,
                resume_at=resume_at.isoformat() if resume_at else None,
            )
        )
        self._state = SessionState.PAUSED
        self._pause_event.clear()

    async def _trigger_auto_resume(self, checkpoint_id: str) -> None:
        await self.resume(checkpoint_id)

    # ------------------------------------------------------------------ #
    # Resume flow (SDD 9.4)
    # ------------------------------------------------------------------ #

    async def resume(self, checkpoint_id: str) -> Checkpoint | None:
        """
        Load checkpoint, refresh budget window if expired, transition to RUNNING.
        Returns the Checkpoint, or None if the checkpoint_id is not found.
        """
        self._state = SessionState.RESUMING
        checkpoint = self._store.load(checkpoint_id)
        if checkpoint is None:
            self._state = SessionState.PAUSED
            return None

        if self._budget.window_remaining.total_seconds() <= 0:
            self._budget.reset_window()

        await self._notifier.send(
            SessionEvent.resumed(
                f"Session resumed from checkpoint {checkpoint_id}",
                checkpoint_id=checkpoint_id,
            )
        )
        self._state = SessionState.RUNNING
        self._pause_event.set()
        return checkpoint

    # ------------------------------------------------------------------ #
    # Helpers
    # ------------------------------------------------------------------ #

    def should_auto_resume(self, now: datetime) -> bool:
        """True if paused, auto_resume is enabled, and the 5-hour window has reset."""
        if self._state != SessionState.PAUSED:
            return False
        return self._auto_resume and self._budget.window_remaining.total_seconds() <= 0

    async def wait_if_paused(self) -> None:
        """Suspend the caller until the session transitions out of PAUSED."""
        await self._pause_event.wait()
