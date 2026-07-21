"""
tasker.tui.messages
-------------------
Textual message classes used for TUI internal events.

SDD_ADDENDUM_PHASE8.md B.5.3 defines these as the bridge point for future
web-dashboard integration: a web surface can broadcast the same event types
over WebSocket while the logic layer stays unchanged.
"""
from __future__ import annotations

from textual.message import Message

from tasker.setup.wizard import WizardStepResult
from tasker.setup.readiness import ReadinessResult
from tasker.workers.base import WorkerManifest


class WizardStepCompleted(Message):
    """Emitted when a setup wizard step finishes, carrying its result."""

    def __init__(self, result: WizardStepResult) -> None:
        super().__init__()
        self.result = result


class ReadinessCheckCompleted(Message):
    """Emitted when a model readiness probe finishes."""

    def __init__(self, result: ReadinessResult) -> None:
        super().__init__()
        self.result = result


class WorkerRegistryUpdated(Message):
    """Emitted when a new worker manifest is written to the registry."""

    def __init__(self, manifest: WorkerManifest) -> None:
        super().__init__()
        self.manifest = manifest

