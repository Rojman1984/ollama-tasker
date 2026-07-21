"""
tasker.tui.screens.setup_wizard
-------------------------------
SetupWizardScreen -- interactive TUI front-end for the headless setup wizard
(tasker.setup.wizard). Runs the same `run_wizard()` logic asynchronously so
the UI stays responsive, shows live per-step status, and lets the user re-run
the whole wizard or individual steps.

See SDD_ADDENDUM_PHASE8.md B.3 / B.5.2 / B.5.5.
"""
from __future__ import annotations

import os
from collections.abc import Callable
from typing import Any

from textual.app import ComposeResult
from textual.containers import Horizontal, VerticalScroll
from textual.screen import Screen
from textual.widgets import Button, Footer, Static

from tasker.setup.wizard import (
    StepStatus,
    WizardStepResult,
    _step1_environment,
    _step2_ollama,
    _step3_hardware,
    _step4_gpu_verify,
    _step5_cache,
    _step6_worker_registry,
    _step7_summary,
    run_wizard,
)
from tasker.tui.messages import WizardStepCompleted
from tasker.tui.widgets.status_bar import HardwareStatusBar
from tasker.tui.widgets.step_row import RerunStepRequested, WizardStepRow


def _ollama_base_url() -> str:
    return os.environ.get("OLLAMA_BASE_URL", "http://localhost:11434")


_StepCallable = Callable[[], list[WizardStepResult] | WizardStepResult]


class SetupWizardScreen(Screen):
    """Interactive setup wizard screen."""

    BINDINGS = [
        ("r", "rerun_gpu", "Re-run GPU verification"),
        ("b", "back", "Back to menu"),
    ]

    DEFAULT_CSS = """
    SetupWizardScreen {
        layout: vertical;
    }
    #wizard-header {
        height: auto;
        padding: 1 2;
    }
    #wizard-title {
        width: 1fr;
        text-style: bold;
    }
    #wizard-actions {
        width: auto;
    }
    #gpu-guidance {
        height: auto;
        margin: 0 2 1 2;
        padding: 1;
        border: round $warning;
        color: $text;
        display: none;
    }
    #gpu-guidance.visible {
        display: block;
    }
    #steps {
        height: 1fr;
        padding: 0 2;
    }
    """

    def __init__(self, base_url: str | None = None, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.base_url = base_url or _ollama_base_url()
        self._results: list[WizardStepResult] = []
        self._wizard_running = False
        self._run_generation = 0

    def compose(self) -> ComposeResult:
        yield HardwareStatusBar()
        with Horizontal(id="wizard-header"):
            yield Static("Setup Wizard", id="wizard-title")
            with Horizontal(id="wizard-actions"):
                yield Button("Re-run All", id="rerun-all", variant="primary")
                yield Button("Back to Menu", id="back", variant="default")
        yield Static("", id="gpu-guidance")
        with VerticalScroll(id="steps"):
            pass
        yield Footer()

    def on_mount(self) -> None:
        self.call_after_refresh(self._start_wizard)

    def _start_wizard(self) -> None:
        if self._wizard_running:
            return
        self._wizard_running = True
        self._run_generation += 1
        # Pass the async method (callable) so Textual's worker runs it.
        self.run_worker(self._run_all_steps)

    async def _run_all_steps(self) -> None:
        """Run the full wizard in a worker and post each result back to the UI."""
        try:
            results = run_wizard(base_url=self.base_url, verbose=False)
            self._results = list(results)
            for result in results:
                self.post_message(WizardStepCompleted(result))
            # Refresh the status bar hardware summary after cache step.
            self._refresh_status_bar()
        finally:
            self._wizard_running = False

    def on_wizard_step_completed(self, event: WizardStepCompleted) -> None:
        self._add_or_update_row(event.result)
        if event.result.step_id == "3.3":
            self._update_gpu_guidance()

    def _add_or_update_row(self, result: WizardStepResult) -> None:
        steps = self.query_one("#steps", VerticalScroll)
        for child in steps.children:
            if (
                isinstance(child, WizardStepRow)
                and child.is_mounted
                and getattr(child, "generation", -1) == self._run_generation
                and child.result.step_id == result.step_id
            ):
                child.update_result(result)
                return
        row = WizardStepRow(result)
        row.generation = self._run_generation
        steps.mount(row)

    def _update_gpu_guidance(self) -> None:
        guidance = self.query_one("#gpu-guidance", Static)
        step_3_3 = next((r for r in self._results if r.step_id == "3.3"), None)
        if step_3_3 is None:
            return
        lines = [f"GPU guidance: {step_3_3.message}"]
        if step_3_3.action_required:
            lines.append(step_3_3.action_required)
        guidance.update("\n".join(lines))
        if step_3_3.action_required or step_3_3.status != StepStatus.OK:
            guidance.add_class("visible")
        else:
            guidance.remove_class("visible")

    def _refresh_status_bar(self) -> None:
        for bar in self.query(HardwareStatusBar):
            bar.refresh_hardware()

    # ------------------------------------------------------------------ #
    # Re-run behavior
    # ------------------------------------------------------------------ #

    def _step_callable(self, step_id: str) -> _StepCallable | None:
        """Map a step id prefix to the underlying wizard step function."""
        prefix = step_id.split(".")[0]
        mapping: dict[str, _StepCallable] = {
            "1": _step1_environment,
            "2": lambda: _step2_ollama(self.base_url),
            "3": _step3_hardware,
            "4": lambda: _step4_gpu_verify(self.base_url),
            "5": _step5_cache,
            "6": _step6_worker_registry,
        }
        return mapping.get(prefix)

    def _rerun_step(self, step_id: str) -> None:
        if self._wizard_running:
            return
        if step_id == "7":
            # Summary is derived from current results; just recompute and update.
            result = _step7_summary(self._results)
            self._add_or_update_row(result)
            return
        fn = self._step_callable(step_id)
        if fn is None:
            return
        self._wizard_running = True

        async def _task() -> None:
            await self._run_single_step(fn, step_id)

        self.run_worker(_task)

    async def _run_single_step(self, fn: _StepCallable, step_id: str) -> None:
        """Run one wizard step function and merge its results back."""
        try:
            outcome = fn()
            results = outcome if isinstance(outcome, list) else [outcome]
            # Replace older results for this step group.
            prefix = step_id.split(".")[0]
            self._results = [r for r in self._results if not r.step_id.startswith(prefix)]
            self._results.extend(results)
            for result in results:
                self.post_message(WizardStepCompleted(result))
            if prefix == "3":
                self._refresh_status_bar()
        finally:
            self._wizard_running = False

    def on_rerun_step_requested(self, event: RerunStepRequested) -> None:
        self._rerun_step(event.step_id)

    # ------------------------------------------------------------------ #
    # Actions and buttons
    # ------------------------------------------------------------------ #

    def action_rerun_gpu(self) -> None:
        self._rerun_step("4")

    def action_back(self) -> None:
        self.app.pop_screen()

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "rerun-all":
            steps = self.query_one("#steps", VerticalScroll)
            steps.remove_children()
            self._results.clear()
            self._start_wizard()
            event.stop()
        elif button_id == "back":
            self.action_back()
            event.stop()
