"""
tasker.modes.code
------------------
CODE mode -- Claude Code analog.
Tools: bash, file_read, file_write, git, linter, test_runner, code_search.
Routing: CAPABILITY_FIRST (coding specialists preferred).
Interaction: CLI/REPL + diffs, await approval on destructive ops.
See SDD Section 5.1.
"""
from __future__ import annotations

# TODO Phase 5