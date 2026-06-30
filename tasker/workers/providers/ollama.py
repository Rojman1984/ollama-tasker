"""
tasker.workers.providers.ollama
--------------------------------
OllamaProvider -- handles LOCAL_HARDWARE and OLLAMA_CLOUD.
Single provider, same endpoint, compute_location distinguishes them.
See SDD Section 5.6.1.
"""
from __future__ import annotations

# TODO Phase 4