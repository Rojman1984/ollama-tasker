"""
tasker.session.checkpoint
--------------------------
Checkpoint dataclass and CheckpointStore.
Persists execution state to enable pause and resume.
Storage: .tasker/checkpoints/<checkpoint_id>.json
See SDD Sections 5.11 and 6.5.
"""
from __future__ import annotations

import itertools
import json
import time
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from tasker.session.budget import BudgetSnapshot
from tasker.workers.base import ExecutionPlan


_STORE_DIR = Path(".tasker") / "checkpoints"

# Monotonic sequence counter so load_latest() is stable when two saves occur
# within the same time.time_ns() tick (common in tests, possible in production
# on low-resolution Windows clocks).  Primary sort key is _save_ns (wall
# clock); _save_seq breaks ties within the same nanosecond.
_SAVE_SEQ: itertools.count = itertools.count()


@dataclass
class Checkpoint:
    """Serialized execution state for pause and resume (SDD 6.5)."""

    id: str
    created_at: datetime
    mode: str
    hardware_profile: str

    # Orchestration state
    original_task: str
    plan: ExecutionPlan
    completed_steps: list[dict]      # serialized WorkerResults
    current_step_index: int
    session_context: dict

    # Memory state
    episodic_log_position: int

    # Budget state at pause time
    budget_snapshot: BudgetSnapshot

    # Resume config
    resume_at: datetime | None
    auto_resume: bool

    @classmethod
    def new(
        cls,
        mode: str,
        hardware_profile: str,
        original_task: str,
        budget_snapshot: BudgetSnapshot,
        plan: ExecutionPlan,
        *,
        completed_steps: list[dict] | None = None,
        current_step_index: int = 0,
        session_context: dict | None = None,
        episodic_log_position: int = 0,
        resume_at: datetime | None = None,
        auto_resume: bool = True,
    ) -> Checkpoint:
        return cls(
            id=str(uuid.uuid4()),
            created_at=datetime.now().astimezone(),
            mode=mode,
            hardware_profile=hardware_profile,
            original_task=original_task,
            plan=plan,
            completed_steps=completed_steps or [],
            current_step_index=current_step_index,
            session_context=session_context or {},
            episodic_log_position=episodic_log_position,
            budget_snapshot=budget_snapshot,
            resume_at=resume_at,
            auto_resume=auto_resume,
        )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "created_at": self.created_at.isoformat(),
            "mode": self.mode,
            "hardware_profile": self.hardware_profile,
            "original_task": self.original_task,
            "plan": self.plan.to_dict(),
            "completed_steps": self.completed_steps,
            "current_step_index": self.current_step_index,
            "session_context": self.session_context,
            "episodic_log_position": self.episodic_log_position,
            "budget_snapshot": self.budget_snapshot.to_dict(),
            "resume_at": self.resume_at.isoformat() if self.resume_at else None,
            "auto_resume": self.auto_resume,
        }

    @classmethod
    def from_dict(cls, data: dict) -> Checkpoint:
        return cls(
            id=data["id"],
            created_at=datetime.fromisoformat(data["created_at"]),
            mode=data["mode"],
            hardware_profile=data["hardware_profile"],
            original_task=data["original_task"],
            plan=ExecutionPlan.from_dict(data["plan"]),
            completed_steps=data["completed_steps"],
            current_step_index=data["current_step_index"],
            session_context=data["session_context"],
            episodic_log_position=data["episodic_log_position"],
            budget_snapshot=BudgetSnapshot.from_dict(data["budget_snapshot"]),
            resume_at=datetime.fromisoformat(data["resume_at"]) if data["resume_at"] else None,
            auto_resume=data["auto_resume"],
        )


class CheckpointStore:
    """Persists Checkpoint objects as JSON at <store_dir>/<checkpoint_id>.json."""

    def __init__(self, store_dir: Path | None = None) -> None:
        self._dir = store_dir if store_dir is not None else _STORE_DIR
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, checkpoint_id: str) -> Path:
        return self._dir / f"{checkpoint_id}.json"

    def save(self, checkpoint: Checkpoint) -> Path:
        path = self._path(checkpoint.id)
        data = checkpoint.to_dict()
        data["_save_ns"]  = time.time_ns()    # wall-clock order across processes
        data["_save_seq"] = next(_SAVE_SEQ)   # strict tiebreaker within this process
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        return path

    def load(self, checkpoint_id: str) -> Checkpoint | None:
        path = self._path(checkpoint_id)
        if not path.exists():
            return None
        return Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))

    def load_latest(self) -> Checkpoint | None:
        # Primary sort key: _save_ns (wall-clock nanoseconds) for cross-process ordering.
        # Tiebreaker: _save_seq (monotonic counter) for saves within the same clock tick,
        # which is common in tests and possible on low-resolution Windows clocks.
        best_raw: dict | None = None
        best_key: tuple[int, int] = (-1, -1)
        for path in self._dir.glob("*.json"):
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                key = (raw.get("_save_ns", 0), raw.get("_save_seq", -1))
                if best_raw is None or key > best_key:
                    best_key = key
                    best_raw = raw
            except (json.JSONDecodeError, KeyError):
                pass
        if best_raw is None:
            return None
        return Checkpoint.from_dict(best_raw)

    def list_all(self) -> list[Checkpoint]:
        result = []
        for path in sorted(
            self._dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime,
            reverse=True,
        ):
            try:
                result.append(
                    Checkpoint.from_dict(json.loads(path.read_text(encoding="utf-8")))
                )
            except (json.JSONDecodeError, KeyError):
                pass
        return result

    def delete(self, checkpoint_id: str) -> bool:
        path = self._path(checkpoint_id)
        if path.exists():
            path.unlink()
            return True
        return False
