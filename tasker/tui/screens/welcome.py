"""
tasker.tui.screens.welcome
----------------------------
WelcomeScreen -- TuiApp's default/home screen (SDD_ADDENDUM_PHASE8.md
B.5.2).

Phase 8.3 scope: renders the full menu shape up front -- Setup Wizard,
Model Selector, Run Task, View Sessions, Daemon -- so 8.4/8.5 don't need
a second navigation-layout change (see B.5.2's note). Only "Quit" is
wired this phase; selecting any other item shows an inert "coming in
Phase 8.x" notice instead of navigating anywhere. Daemon is a permanent
placeholder per B.6 ("Phase 8 TUI must reserve a Daemon menu item...
without implementing it").
"""
from __future__ import annotations

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import Screen
from textual.widgets import Footer, Label, ListItem, ListView, Static

from tasker.tui.screens.model_selector import ModelSelectorScreen
from tasker.tui.screens.setup_wizard import SetupWizardScreen
from tasker.tui.widgets.status_bar import HardwareStatusBar

# (key, label, notice-shown-on-select)
MENU_ITEMS: list[tuple[str, str, str]] = [
    ("setup_wizard", "Setup Wizard", "Coming in Phase 8.4 -- use `tasker-setup` for now."),
    ("model_selector", "Model Selector", "Coming in Phase 8.4 -- use `tasker-setup --check-model <name>` for now."),
    ("run_task", "Run Task", "Coming in Phase 8.5 -- use `tasker-cli` for now."),
    ("view_sessions", "View Sessions", "Coming in Phase 8.5 -- use `tasker-cli checkpoints` for now."),
    ("daemon", "Daemon", "Not yet implemented -- reserved per SDD_ADDENDUM_PHASE8.md B.6."),
]


class WelcomeScreen(Screen):
    """Status bar + main menu. Default screen TuiApp pushes on mount."""

    BINDINGS = [("q", "quit_app", "Quit")]

    DEFAULT_CSS = """
    WelcomeScreen {
        align: center middle;
    }
    #menu {
        width: 60;
        height: auto;
        border: round $primary;
        padding: 1 2;
    }
    #title {
        text-style: bold;
        content-align: center middle;
        margin-bottom: 1;
    }
    #menu-notice {
        margin-top: 1;
        color: $text-muted;
    }
    """

    def compose(self) -> ComposeResult:
        yield HardwareStatusBar()
        with Vertical(id="menu"):
            yield Static("Ollama Tasker", id="title")
            yield ListView(
                *[ListItem(Label(label), id=f"menu-{key}") for key, label, _ in MENU_ITEMS],
                ListItem(Label("Quit"), id="menu-quit"),
                id="menu-list",
            )
            yield Static("", id="menu-notice")
        yield Footer()

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        if event.item.id == "menu-quit":
            self.action_quit_app()
            return
        key, label, notice = MENU_ITEMS[event.index]
        if key == "setup_wizard":
            self.app.push_screen(SetupWizardScreen())
            return
        if key == "model_selector":
            self.app.push_screen(ModelSelectorScreen())
            return
        self.query_one("#menu-notice", Static).update(f"{label}: {notice}")

    def action_quit_app(self) -> None:
        self.app.exit()
