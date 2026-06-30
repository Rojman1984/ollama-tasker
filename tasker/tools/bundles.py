"""
tasker.tools.bundles
---------------------
Tool bundle definitions per mode.

CHAT:     search, calculator, memory_read
CODE:     bash, file_read, file_write, git, linter, test_runner, code_search
COWORK:   ALL + checkpoint_write, task_state, progress_report
RESEARCH: web_search, retrieve, pdf_extract, citation_tracker
SECURE:   file_read, file_write, local_search, local_memory (NO web tools)
See SDD Section 5.1.
"""
from __future__ import annotations

# TODO Phase 5