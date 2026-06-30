"""
tasker.session.manager
-----------------------
SessionManager -- full lifecycle state machine.

States: RUNNING -> THROTTLING -> PAUSING -> CHECKPOINTING -> PAUSED -> RESUMING
Called before every worker dispatch via tick().
See SDD Sections 5.8 and 9.
"""
from __future__ import annotations

# TODO Phase 2