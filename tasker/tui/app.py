"""
tasker.tui.app
----------------
TuiApp -- the `tasker` console script's entry point (Textual full-screen
TUI, SDD_ADDENDUM_PHASE8.md B.5). Phase 8.3 scope: TuiApp + WelcomeScreen
+ HardwareStatusBar only (B.11's checklist, not B.8's shorter roadmap
table -- see the addendum's 2026-07-19 reconciliation note in B.8).
SetupWizardScreen + ModelSelectorScreen are Phase 8.4; HarnessPanel is
Phase 8.5.

Supersedes the rudimentary stdlib REPL that lived here for one session
(B.5.0) -- that REPL was documented from the start as a deliberate,
temporary interim ahead of this Textual app, not something meant to be
reused by it. Its production-dispatch logic was already extracted into
`tasker/runtime/dispatch.py` before this session, specifically so it
would survive the REPL's removal and be available to HarnessPanel (8.5)
and SetupWizardScreen/ModelSelectorScreen (8.4) later -- nothing here
duplicates it. The REPL itself (`_repl()`/`_dispatch()`) is gone; for an
interactive multi-turn CLI session in the meantime, use `tasker-cli
shell`.
"""
from __future__ import annotations

from textual.app import App

from tasker.tui.screens.welcome import WelcomeScreen


class TuiApp(App):
    """Ollama Tasker's full-screen terminal application."""

    TITLE = "Ollama Tasker"
    CSS = """
    Screen {
        background: $surface;
    }
    """

    def on_mount(self) -> None:
        self.push_screen(WelcomeScreen())


def main() -> None:
    """Entry point for the `tasker` console script."""
    import logging
    import os

    logging.basicConfig(
        level=os.environ.get("TASKER_LOG_LEVEL", "WARNING").upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    TuiApp().run()


if __name__ == "__main__":
    main()
