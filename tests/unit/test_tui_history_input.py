"""
Unit tests -- tasker/tui/widgets/history_input.py
SDD_ADDENDUM_PHASE8.md B.5.5 (history recall, reverse search, tab completion).
"""
import tempfile
import unittest
from pathlib import Path

from textual.app import App, ComposeResult
from textual.widgets import Input, OptionList, Static

from tasker.tui.widgets.history_input import (
    HistoryInput,
    ReverseSearchScreen,
    _read_history_lines,
    _write_history_lines,
)


class _TestApp(App):
    """Minimal app hosting a HistoryInput for headless Pilot testing."""

    def __init__(self, history_path: Path, completer=None) -> None:
        super().__init__()
        self.history_path = history_path
        self.completer = completer
        self.input_value = None

    def compose(self) -> ComposeResult:
        yield HistoryInput(
            id="input",
            history_path=self.history_path,
            completer=self.completer,
        )
        yield Static(id="echo")

    def on_input_submitted(self, event) -> None:
        self.input_value = event.value
        self.query_one("#echo", Static).update(str(event.value))


class TestHistoryFileIO(unittest.TestCase):

    def test_read_plain_lines(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("line one\nline two\n")
            path = Path(f.name)
        self.assertEqual(_read_history_lines(path), ["line one", "line two"])
        path.unlink()

    def test_read_readline_timestamp_format(self):
        with tempfile.NamedTemporaryFile("w", delete=False) as f:
            f.write("#1234567890\ncommand one\n#1234567891\ncommand two\n")
            path = Path(f.name)
        self.assertEqual(_read_history_lines(path), ["command one", "command two"])
        path.unlink()

    def test_write_then_read_roundtrip(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "hist"
            _write_history_lines(path, ["alpha", "beta"], max_lines=10)
            self.assertEqual(_read_history_lines(path), ["alpha", "beta"])


class TestHistoryRecall(unittest.IsolatedAsyncioTestCase):

    async def asyncSetUp(self):
        self.tmpdir = tempfile.TemporaryDirectory()
        self.history_path = Path(self.tmpdir.name) / "history"
        self.history_path.write_text("alpha\nbeta\ngamma\n", encoding="utf-8")

    async def asyncTearDown(self):
        self.tmpdir.cleanup()

    async def test_up_down_recall(self):
        app = _TestApp(self.history_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            inp = app.query_one("#input", HistoryInput)
            self.assertEqual(inp.value, "")
            await pilot.press("up")
            self.assertEqual(inp.value, "gamma")
            await pilot.press("up")
            self.assertEqual(inp.value, "beta")
            await pilot.press("down")
            self.assertEqual(inp.value, "gamma")
            await pilot.press("down")
            self.assertEqual(inp.value, "")

    async def test_submit_appends_history(self):
        app = _TestApp(self.history_path)
        async with app.run_test() as pilot:
            await pilot.pause()
            inp = app.query_one("#input", HistoryInput)
            inp.value = "new-entry"
            await pilot.press("enter")
            await pilot.pause()
            self.assertIn("new-entry", _read_history_lines(self.history_path))
            self.assertEqual(app.input_value, "new-entry")


class TestReverseSearch(unittest.IsolatedAsyncioTestCase):

    async def test_reverse_search_overlay(self):
        with tempfile.TemporaryDirectory() as d:
            history_path = Path(d) / "history"
            history_path.write_text("one\ntwo\nthree\n", encoding="utf-8")
            app = _TestApp(history_path)
            async with app.run_test() as pilot:
                await pilot.pause()
                await pilot.press("ctrl+r")
                await pilot.pause()
                # Modal screen should now be on top.
                self.assertIsInstance(app.screen, ReverseSearchScreen)
                # Filter to "t".
                screen = app.screen
                screen.query_one("#search-input", Input).value = "t"
                await pilot.pause()
                # Two matches (most-recent first): three, two.
                options = screen.query_one("#search-options", OptionList)
                self.assertEqual(
                    [str(o.prompt) for o in options.options],
                    ["three", "two"],
                )


class TestTabCompletion(unittest.IsolatedAsyncioTestCase):

    async def test_tab_cycles_prefix_matches(self):
        def completer(value: str) -> list[str]:
            return ["alpha", "alphabet", "beta"]

        with tempfile.TemporaryDirectory() as d:
            app = _TestApp(Path(d) / "history", completer=completer)
            async with app.run_test() as pilot:
                await pilot.pause()
                inp = app.query_one("#input", HistoryInput)
                inp.value = "alp"
                await pilot.press("tab")
                self.assertEqual(inp.value, "alpha")
                await pilot.press("tab")
                self.assertEqual(inp.value, "alphabet")
                await pilot.press("tab")
                self.assertEqual(inp.value, "alpha")
