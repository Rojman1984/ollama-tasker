"""
tasker.modes.research
----------------------
RESEARCH mode -- deep research.
Parallel fetch + long-context synthesis. Citation tracking.
Workers: minimax-m3 (1M ctx) for synthesis, local for fetch steps.
See SDD Section 5.1.
"""
from __future__ import annotations

# TODO Phase 5