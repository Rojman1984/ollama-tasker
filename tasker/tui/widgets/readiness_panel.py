"""
tasker.tui.widgets.readiness_panel
----------------------------------
ReadinessReportPanel -- displays the output of the agentic readiness checker
(format_report) and provides an explicit "Copy to clipboard" fallback so the
user can capture the report even if their terminal emulator's native mouse
selection is blocked by Textual's mouse capture.

Per SDD_ADDENDUM_PHASE8.md B.5.5, native click-drag selection in the report
panel must be manually verified in a real terminal; the copy button is the
required in-app fallback.
"""
from __future__ import annotations

from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, Vertical
from textual.widgets import Button, Static

from tasker.setup.readiness import ReadinessResult, format_report


class ReadinessReportPanel(Vertical):
    """Right-hand panel on ModelSelectorScreen: formatted readiness report."""

    DEFAULT_CSS = """
    ReadinessReportPanel {
        height: 1fr;
        border: round $primary;
        padding: 1 2;
    }
    #report-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #report-content {
        height: 1fr;
        width: 100%;
        padding: 1;
    }
    #report-actions {
        height: auto;
        margin-top: 1;
    }
    #progress {
        height: auto;
        margin-top: 1;
        color: $text-muted;
    }
    """

    def __init__(self, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._result: ReadinessResult | None = None

    def compose(self) -> ComposeResult:
        yield Static("Readiness Report", id="report-title")
        yield Static(
            "Select a model from the list or type a model tag, then press "
            "\"Test Model\" to run the readiness probe.",
            id="report-content",
        )
        with Horizontal(id="report-actions"):
            yield Button("Copy report", id="copy-report", disabled=True)
        yield Static("", id="progress")

    def show_progress(self, message: str) -> None:
        """Show a progress/status line and disable copy until a result exists."""
        self.query_one("#progress", Static).update(message)
        self.query_one("#copy-report", Button).disabled = True
        self._result = None

    def show_result(self, result: ReadinessResult) -> None:
        """Display a completed readiness result."""
        self._result = result
        self.query_one("#report-content", Static).update(format_report(result))
        self.query_one("#progress", Static).update("")
        self.query_one("#copy-report", Button).disabled = False

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "copy-report" and self._result is not None:
            try:
                self.app.copy_to_clipboard(format_report(self._result))
                self.app.notify("Report copied to clipboard", severity="information", timeout=2)
            except Exception:
                self.app.notify(
                    "Could not copy to clipboard -- use terminal selection instead",
                    severity="error",
                    timeout=3,
                )
            event.stop()
