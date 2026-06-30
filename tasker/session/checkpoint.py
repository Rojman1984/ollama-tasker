"""
tasker.session.checkpoint
--------------------------
Checkpoint dataclass and CheckpointStore.
Persists execution state to enable pause and resume.
Storage: .tasker/checkpoints/<checkpoint_id>.json
See SDD Sections 5.11 and 6.5.
"""
from __future__ import annotations

# TODO Phase 2