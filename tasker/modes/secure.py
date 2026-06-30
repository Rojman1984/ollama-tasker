"""
tasker.modes.secure
--------------------
SECURE mode -- LOCAL_ONLY hard block.
ANY cloud call raises TaskerPolicyError immediately.
No silent fallback. Banner shown on every response.
See SDD Sections 5.1 and 11.
"""
from __future__ import annotations

# TODO Phase 5