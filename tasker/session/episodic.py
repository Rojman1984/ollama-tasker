"""
tasker.session.episodic
------------------------
EpisodicMemoryBridge ABC and concrete implementations for COWORK mode.

This is an interface stub — it defines the contract that a real MindSeed
dual-store implementation would satisfy, without reimplementing MindSeed
itself.  The bridge is intentionally minimal: record an event, read events
since a given position.  CoworkRunner calls record_event() at each step
boundary and persists episodic_log_position into the Checkpoint so that
resume can continue from the right point.

Implementations:
  NullEpisodicMemoryBridge   -- no-op, the default (no file I/O)
  JsonlEpisodicMemoryBridge  -- appends events to a .jsonl file per session

See SDD Section 5.11 (episodic_log_position on Checkpoint) and the COWORK
mode description in Section 5.1.
"""
from __future__ import annotations

import json
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path


# --------------------------------------------------------------------------- #
# ABC
# --------------------------------------------------------------------------- #

class EpisodicMemoryBridge(ABC):
    """
    Minimal interface for episodic event storage.

    record_event(session_id, event) — append one event dict.  Returns the
        log position of the newly written event (0-indexed line number for
        JSONL backends).
    read_since(session_id, position) — return all events from position
        onwards (inclusive).  position=0 returns the full history.
    """

    @abstractmethod
    def record_event(self, session_id: str, event: dict) -> int:
        """Persist event and return its log position."""

    @abstractmethod
    def read_since(self, session_id: str, position: int) -> list[dict]:
        """Return events from position onwards (inclusive)."""


# --------------------------------------------------------------------------- #
# NullEpisodicMemoryBridge
# --------------------------------------------------------------------------- #

class NullEpisodicMemoryBridge(EpisodicMemoryBridge):
    """No-op bridge — discards all events. Default for modes that don't need episodic memory."""

    def record_event(self, session_id: str, event: dict) -> int:
        return 0

    def read_since(self, session_id: str, position: int) -> list[dict]:
        return []


# --------------------------------------------------------------------------- #
# JsonlEpisodicMemoryBridge
# --------------------------------------------------------------------------- #

class JsonlEpisodicMemoryBridge(EpisodicMemoryBridge):
    """
    Appends events to <store_dir>/<session_id>.jsonl — one JSON object per line.
    log_position is the 0-indexed line number.  Suitable for local COWORK
    sessions without the real MindSeed system.
    """

    def __init__(self, store_dir: Path) -> None:
        self._dir = store_dir
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, session_id: str) -> Path:
        return self._dir / f"{session_id}.jsonl"

    def record_event(self, session_id: str, event: dict) -> int:
        path = self._path(session_id)
        stamped = {"_ts": datetime.now().astimezone().isoformat(), **event}
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(stamped) + "\n")
        # Count lines to determine position of the just-written entry
        return sum(1 for _ in path.open(encoding="utf-8")) - 1

    def read_since(self, session_id: str, position: int) -> list[dict]:
        path = self._path(session_id)
        if not path.exists():
            return []
        events = []
        with path.open(encoding="utf-8") as fh:
            for i, line in enumerate(fh):
                if i >= position:
                    line = line.strip()
                    if line:
                        try:
                            events.append(json.loads(line))
                        except json.JSONDecodeError:
                            pass
        return events
