"""
tasker.orchestrator.tier1_single
----------------------------------
SingleLLMOrchestrator (Tier 1).
One small model, role-switched via system prompt.
Sequential load: load -> plan -> unload -> worker runs.
Target: TASKER-P1 normal operation (qwen3:1.7b or llama3.2:3b).
See SDD Section 5.3.
"""
from __future__ import annotations

# TODO Phase 3