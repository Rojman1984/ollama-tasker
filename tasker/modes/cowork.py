"""
tasker.modes.cowork
--------------------
COWORK mode -- Claude Cowork analog.
Full plan/checkpoint loop. TRINITY-lite orchestration.
Routing: HYBRID. Interaction: async + checkpoint events, resumable.
Memory: project + episodic (MindSeed-compatible).
See SDD Section 5.1.
"""
from __future__ import annotations

# TODO Phase 5