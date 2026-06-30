"""
tasker.modes.chat
------------------
CHAT mode -- lightweight conversational.
Orchestrator: Tier 0-1, single worker, no planning loop.
Routing: COST_OPTIMIZED. Interaction: sync stream.
See SDD Section 5.1.
"""
from __future__ import annotations

# TODO Phase 5