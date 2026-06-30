"""
tasker.session.budget
----------------------
OllamaSessionBudget -- 5-hour rolling window tracker.
Throttle routing at 90%. Begin pause flow at 100%.
See SDD Sections 5.10 and 6.6.
"""
from __future__ import annotations

# TODO Phase 2
#
# @dataclass
# class OllamaSessionBudget:
#     plan: OllamaPlan
#     window_start: datetime
#     window_duration: timedelta = timedelta(hours=5)
#     usage_consumed: float = 0.0
#     weekly_usage_consumed: float = 0.0
#
#     @property
#     def usage_pct(self) -> float: ...
#     @property
#     def should_throttle(self) -> bool: ...   # usage_pct >= 0.90
#     @property
#     def is_exhausted(self) -> bool: ...      # usage_pct >= 1.0