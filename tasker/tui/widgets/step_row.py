"""
tasker.tui.widgets.step_row
---------------------------
WizardStepRow -- one visual row for a WizardStepResult. Shows step id,
name, colored status icon, message, collapsible detail, and any action
the user must run. Emits no messages of its own; the parent screen handles
"Re-run Step" clicks.
"""
from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.message import Message
from textual.widgets import Button, Static

from tasker.setup.wizard import StepStatus, WizardStepResult


class RerunStepRequested(Message):
    """Posted by a WizardStepRow when its "Re-run Step" button is pressed."""

    def __init__(self, step_id: str) -> None:
        super().__init__()
        self.step_id = step_id


_STATUS_ICON = {
    StepStatus.OK: "✓",
    StepStatus.WARNING: "▲",
    StepStatus.ERROR: "✗",
    StepStatus.SKIPPED: "⊘",
}

_STATUS_CLASS = {
    StepStatus.OK: "status-ok",
    StepStatus.WARNING: "status-warning",
    StepStatus.ERROR: "status-error",
    StepStatus.SKIPPED: "status-skipped",
}


class WizardStepRow(Vertical):
    """Collapsible visual representation of a single wizard step result."""

    DEFAULT_CSS = """
    WizardStepRow {
        height: auto;
        border: solid $primary-darken-2;
        padding: 0 1;
        margin: 1 0;
    }
    WizardStepRow Static {
        height: auto;
    }
    #header {
        height: auto;
        margin: 1 0;
    }
    #status-icon {
        width: 3;
        content-align: center middle;
    }
    #step-id {
        width: 6;
        color: $text-muted;
    }
    #step-name {
        width: 1fr;
        text-style: bold;
    }
    #message {
        margin: 1 0;
    }
    #detail {
        margin: 1 0 1 4;
        color: $text-muted;
        display: none;
    }
    #detail.visible {
        display: block;
    }
    #action {
        margin: 1 0 1 4;
        color: $warning;
        text-style: italic;
    }
    #copy-action {
        margin: 0 0 1 4;
        width: auto;
    }
    #rerun-step {
        margin: 0 0 1 4;
        width: auto;
    }
    .status-ok { color: $success; }
    .status-warning { color: $warning; }
    .status-error { color: $error; }
    .status-skipped { color: $text-muted; }
    """

    def __init__(self, result: WizardStepResult, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.result = result

    def compose(self) -> ComposeResult:
        with Horizontal(id="header"):
            yield Static(_STATUS_ICON[self.result.status], id="status-icon", classes=_STATUS_CLASS[self.result.status])
            yield Static(self.result.step_id, id="step-id")
            yield Static(self.result.step_name, id="step-name")
        yield Static(self.result.message, id="message")
        yield Static(self.result.detail or "", id="detail", classes="visible" if self.result.detail else "")
        if self.result.action_required:
            yield Static(self.result.action_required, id="action")
            yield Button("Copy command", id="copy-action", variant="primary")
        yield Button("Re-run Step", id="rerun-step", variant="default")

    def update_result(self, result: WizardStepResult) -> None:
        """Refresh the row in place when a re-run produces a new result."""
        self.result = result
        self.query_one("#status-icon", Static).update(_STATUS_ICON[result.status])
        self.query_one("#status-icon", Static).set_classes(_STATUS_CLASS[result.status])
        self.query_one("#step-id", Static).update(result.step_id)
        self.query_one("#step-name", Static).update(result.step_name)
        self.query_one("#message", Static).update(result.message)
        detail = self.query_one("#detail", Static)
        detail.update(result.detail or "")
        if result.detail:
            detail.add_class("visible")
        else:
            detail.remove_class("visible")
        action = self.query_one("#action", Static)
        copy_button = self.query_one("#copy-action", Button)
        action.update(result.action_required or "")
        if result.action_required:
            action.styles.display = "block"
            copy_button.styles.display = "block"
        else:
            action.styles.display = "none"
            copy_button.styles.display = "none"

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "copy-action" and self.result.action_required:
            try:
                self.app.copy_to_clipboard(self.result.action_required)
                self.app.notify("Copied command to clipboard", severity="information", timeout=2)
            except Exception:
                self.app.notify("Could not copy to clipboard", severity="error", timeout=3)
            event.stop()
        elif button_id == "rerun-step":
            self.post_message(RerunStepRequested(self.result.step_id))
            event.stop()
