"""
tasker.tui.widgets.history_input
--------------------------------
Reusable Input subclass with persistent history stored in the same file the
REPL uses (`~/.tasker_history` by default). Provides Up/Down history recall,
Ctrl+R reverse-search overlay, and optional tab-completion cycling.

This is intentionally a *widget*, not a screen-level concern, so any TUI
screen with a text input (SetupWizardScreen, ModelSelectorScreen,
HarnessPanel) can drop it in.
"""
from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import Any

from textual.app import ComposeResult
from textual.containers import Vertical
from textual.screen import ModalScreen
from textual.suggester import Suggester
from textual.binding import Binding
from textual.widgets import Input, Label, OptionList
from textual import events


_DEFAULT_HISTORY_PATH = Path.home() / ".tasker_history"
_HISTORY_MAX_LINES = 1000


# --------------------------------------------------------------------------- #
# History file I/O -- compatible with the REPL's readline-backed store
# --------------------------------------------------------------------------- #

def _read_history_lines(path: Path) -> list[str]:
    """Read a readline-style history file, tolerating both plain lines and
    GNU timestamp lines ("#1234567890").
    """
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines: list[str] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line.startswith("#"):
            # GNU readline timestamp line -- skip it, the command is the next line.
            continue
        lines.append(line)
    return lines


def _write_history_lines(path: Path, lines: list[str], max_lines: int) -> None:
    """Write history back to disk. Prefer the readline module when available
    so the file stays in readline's native timestamped format; fall back to
    plain text otherwise.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    trimmed = lines[-max_lines:] if len(lines) > max_lines else lines
    try:
        import readline
    except ImportError:
        readline = None  # type: ignore[assignment]

    if readline is not None:
        try:
            readline.clear_history()
            for line in trimmed:
                readline.add_history(line)
            readline.set_history_length(max_lines)
            readline.write_history_file(str(path))
            return
        except Exception:
            pass

    # Plain-text fallback.
    try:
        path.write_text("\n".join(trimmed) + "\n", encoding="utf-8")
    except OSError:
        pass


# --------------------------------------------------------------------------- #
# Reverse-search modal
# --------------------------------------------------------------------------- #

class ReverseSearchScreen(ModalScreen[str | None]):
    """Filterable history picker. Dismisses with the selected string or None."""

    BINDINGS = [("escape", "dismiss(None)", "Cancel")]

    DEFAULT_CSS = """
    ReverseSearchScreen {
        align: center middle;
    }
    #search-dialog {
        width: 60;
        height: auto;
        max-height: 20;
        border: round $primary;
        background: $surface;
        padding: 1 2;
    }
    #search-title {
        text-style: bold;
        margin-bottom: 1;
    }
    #search-options {
        height: auto;
        max-height: 12;
        border: none;
    }
    """

    def __init__(self, history: list[str], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        # Most recent first.
        self._history = list(reversed(history))
        self._filtered: list[str] = list(self._history)

    def compose(self) -> ComposeResult:
        with Vertical(id="search-dialog"):
            yield Label("Reverse history search (Ctrl+R)", id="search-title")
            yield Input(placeholder="type to filter, Enter to select, Esc to cancel", id="search-input")
            yield OptionList(*self._history, id="search-options")

    def on_mount(self) -> None:
        self.query_one("#search-input", Input).focus()

    def _refresh_options(self, value: str) -> None:
        value_lower = value.lower()
        self._filtered = [h for h in self._history if value_lower in h.lower()]
        option_list = self.query_one("#search-options", OptionList)
        option_list.clear_options()
        option_list.add_options(self._filtered)
        if option_list.option_count:
            option_list.highlighted = 0

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "search-input":
            self._refresh_options(event.value)

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        idx = event.option_index
        if 0 <= idx < len(self._filtered):
            self.dismiss(self._filtered[idx])

    def action_dismiss(self, result: str | None) -> None:
        self.dismiss(result)


# --------------------------------------------------------------------------- #
# Inline suggester for prefix matches
# --------------------------------------------------------------------------- #

class _CompletionSuggester(Suggester):
    """Async suggester that asks a sync callback for candidates and returns the
    first prefix match as the inline suggestion.
    """

    def __init__(self, completer: Callable[[str], list[str]], **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self._completer = completer

    async def get_suggestion(self, value: str) -> str | None:
        value_lower = value.casefold()
        for candidate in self._completer(value):
            if candidate.casefold().startswith(value_lower):
                return candidate
        return None


# --------------------------------------------------------------------------- #
# History input widget
# --------------------------------------------------------------------------- #

class HistoryInput(Input):
    """Input with Up/Down history recall, Ctrl+R reverse search, and optional
    tab-completion cycling.

    Args:
        history_path: file used for persistent history. Defaults to ~/.tasker_history.
        max_history: maximum number of entries to keep on disk.
        completer: optional callback(value) -> list[str] used for both inline
            suggestions and Tab cycling.
    """

    BINDINGS = [
        ("up", "history_prev", "History previous"),
        ("down", "history_next", "History next"),
        ("ctrl+r", "reverse_search", "Reverse search"),
        Binding("tab", "complete", "Complete", priority=True),
        Binding("shift+tab", "complete_backward", "Complete backward", priority=True),
    ]

    def __init__(
        self,
        *args: Any,
        history_path: Path | str | None = None,
        max_history: int = _HISTORY_MAX_LINES,
        completer: Callable[[str], list[str]] | None = None,
        **kwargs: Any,
    ) -> None:
        suggester = _CompletionSuggester(completer) if completer is not None else None
        super().__init__(*args, suggester=suggester, **kwargs)
        self._history_path = Path(history_path) if history_path is not None else _DEFAULT_HISTORY_PATH
        self._max_history = max_history
        self._completer = completer
        self._history: list[str] = []
        self._history_index: int | None = None
        self._original_value: str = ""
        self._completion_matches: list[str] = []
        self._completion_index: int = -1
        self._ignore_change: bool = False

    def on_mount(self) -> None:
        self._history = _read_history_lines(self._history_path)

    # ------------------------------------------------------------------ #
    # History recall
    # ------------------------------------------------------------------ #

    def action_history_prev(self) -> None:
        if not self._history:
            return
        if self._history_index is None:
            self._original_value = self.value
            self._history_index = len(self._history) - 1
        elif self._history_index > 0:
            self._history_index -= 1
        else:
            return
        self.value = self._history[self._history_index]
        self.action_end()

    def action_history_next(self) -> None:
        if self._history_index is None:
            return
        if self._history_index < len(self._history) - 1:
            self._history_index += 1
            self.value = self._history[self._history_index]
        else:
            self.value = self._original_value
            self._history_index = None
        self.action_end()

    def action_reverse_search(self) -> None:
        self.app.push_screen(ReverseSearchScreen(self._history), self._on_search_select)

    def _on_search_select(self, result: str | None) -> None:
        if result is not None:
            self.value = result
            self.action_end()

    # ------------------------------------------------------------------ #
    # Tab completion cycling
    # ------------------------------------------------------------------ #

    def _prefix_matches(self, value: str) -> list[str]:
        if self._completer is None:
            return []
        value_lower = value.casefold()
        return [c for c in self._completer(value) if c.casefold().startswith(value_lower)]

    def _apply_completion(self, value: str) -> None:
        self._ignore_change = True
        try:
            self.value = value
            self.action_end()
        finally:
            self._ignore_change = False

    def action_complete(self) -> None:
        value = self.value
        if not value:
            return
        if self._completion_index == -1 or not self._completion_matches:
            self._completion_matches = self._prefix_matches(value)
            self._completion_index = 0
        else:
            self._completion_index = (self._completion_index + 1) % len(self._completion_matches)
        if self._completion_matches:
            self._apply_completion(self._completion_matches[self._completion_index])

    def action_complete_backward(self) -> None:
        if not self._completion_matches:
            self._completion_matches = self._prefix_matches(self.value)
        if not self._completion_matches:
            return
        if self._completion_index == -1:
            self._completion_index = len(self._completion_matches) - 1
        else:
            self._completion_index = (self._completion_index - 1) % len(self._completion_matches)
        self._apply_completion(self._completion_matches[self._completion_index])

    async def _on_key(self, event: events.Key) -> None:
        await super()._on_key(event)
        # Reset completion cycle when the user types a printable character.
        if event.is_printable:
            self._completion_index = -1
            self._completion_matches = []

    # ------------------------------------------------------------------ #
    # Persistence on submit
    # ------------------------------------------------------------------ #

    def on_input_submitted(self, event: Input.Submitted) -> None:
        value = event.value.strip()
        if value and (not self._history or self._history[-1] != value):
            self._history.append(value)
            _write_history_lines(self._history_path, self._history, self._max_history)
        self._history_index = None
        self._original_value = ""
