"""
tasker.session.budget
----------------------
OllamaSessionBudget -- 5-hour rolling window tracker.
BudgetSnapshot      -- point-in-time serializable snapshot.

Throttle routing at 90%. Begin pause flow at 100%.
See SDD Sections 5.10 and 6.6.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta

from tasker.workers.base import OllamaPlan


# GPU-time units consumed per 5-hour session window before throttle / pause.
# Chosen to be round numbers; exact Ollama Cloud limits are not published.
_SESSION_LIMIT: dict[OllamaPlan, float] = {
    OllamaPlan.FREE: 1_000.0,
    OllamaPlan.PRO:  3_000.0,
    OllamaPlan.MAX: 10_000.0,
}

_WEEKLY_LIMIT: dict[OllamaPlan, float] = {
    OllamaPlan.FREE:  5_000.0,
    OllamaPlan.PRO:  15_000.0,
    OllamaPlan.MAX:  50_000.0,
}

_THROTTLE_PCT   = 0.90
_EXHAUST_PCT    = 1.00
_WEEKLY_WARN_PCT = 0.85


@dataclass
class OllamaSessionBudget:
    """
    Tracks GPU-time usage against the current 5-hour Ollama Cloud window.

    Usage units are accumulated via record_usage(). Signals (should_throttle,
    is_exhausted) are consumed by SessionManager.tick() to drive state transitions.
    """
    plan: OllamaPlan
    window_start: datetime
    window_duration: timedelta = field(default_factory=lambda: timedelta(hours=5))
    usage_consumed: float = 0.0
    weekly_usage_consumed: float = 0.0

    # ------------------------------------------------------------------ #
    # Limits (derived from plan)
    # ------------------------------------------------------------------ #

    @property
    def session_limit(self) -> float:
        return _SESSION_LIMIT[self.plan]

    @property
    def weekly_limit(self) -> float:
        return _WEEKLY_LIMIT[self.plan]

    # ------------------------------------------------------------------ #
    # Computed properties  (SDD 6.6)
    # ------------------------------------------------------------------ #

    @property
    def usage_pct(self) -> float:
        return self.usage_consumed / self.session_limit

    @property
    def weekly_usage_pct(self) -> float:
        return self.weekly_usage_consumed / self.weekly_limit

    @property
    def window_remaining(self) -> timedelta:
        now = datetime.now(tz=self.window_start.tzinfo)
        elapsed = now - self.window_start
        return max(timedelta(0), self.window_duration - elapsed)

    @property
    def should_throttle(self) -> bool:
        """True when session usage >= 90% or weekly usage >= 85%."""
        return self.usage_pct >= _THROTTLE_PCT or self.weekly_usage_pct >= _WEEKLY_WARN_PCT

    @property
    def is_exhausted(self) -> bool:
        """True when session usage >= 100% or weekly usage >= 100%."""
        return self.usage_pct >= _EXHAUST_PCT or self.weekly_usage_pct >= _EXHAUST_PCT

    # ------------------------------------------------------------------ #
    # Mutation helpers
    # ------------------------------------------------------------------ #

    def record_usage(self, units: float) -> None:
        """Accumulate GPU-time units from a completed provider call."""
        self.usage_consumed += units
        self.weekly_usage_consumed += units

    def reset_window(self) -> None:
        """Reset the 5-hour window (called when a new window opens)."""
        self.window_start = datetime.now(tz=self.window_start.tzinfo)
        self.usage_consumed = 0.0

    def snapshot(self) -> BudgetSnapshot:
        return BudgetSnapshot.from_budget(self)


@dataclass
class BudgetSnapshot:
    """Point-in-time snapshot of budget state — stored inside a Checkpoint."""
    captured_at: datetime
    usage_pct: float
    weekly_usage_pct: float
    window_remaining_s: float
    plan: str

    @classmethod
    def from_budget(cls, budget: OllamaSessionBudget) -> BudgetSnapshot:
        return cls(
            captured_at=datetime.now(tz=budget.window_start.tzinfo),
            usage_pct=budget.usage_pct,
            weekly_usage_pct=budget.weekly_usage_pct,
            window_remaining_s=budget.window_remaining.total_seconds(),
            plan=budget.plan.value,
        )

    def to_dict(self) -> dict:
        return {
            "captured_at": self.captured_at.isoformat(),
            "usage_pct": self.usage_pct,
            "weekly_usage_pct": self.weekly_usage_pct,
            "window_remaining_s": self.window_remaining_s,
            "plan": self.plan,
        }

    @classmethod
    def from_dict(cls, data: dict) -> BudgetSnapshot:
        return cls(
            captured_at=datetime.fromisoformat(data["captured_at"]),
            usage_pct=data["usage_pct"],
            weekly_usage_pct=data["weekly_usage_pct"],
            window_remaining_s=data["window_remaining_s"],
            plan=data["plan"],
        )
