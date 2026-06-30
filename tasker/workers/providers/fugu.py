"""
tasker.workers.providers.fugu
------------------------------
FuguProvider -- Sakana Fugu OpenAI-compat endpoint.
Fugu is registered with Capability.MULTI_AGENT. It internally
orchestrates its own pool and returns a synthesized result.
See SDD Section 5.6.4.
"""
from __future__ import annotations

# TODO Phase 4