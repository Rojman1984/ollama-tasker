"""
Unit tests -- cli/shell.py readline integration (2026-07-20 REPL/TUI UX
sprint, part 3): persistent history, tab-completion. Never touches the
real ~/.tasker_history -- every test passes an explicit tmp path or
mocks the readline module entirely.

Arrow-key editing and Ctrl-R reverse search are GNU readline features
that come free from importing the readline module and are exercised by
a real terminal, not something a headless test can assert on directly --
covered here is everything this project's own code controls: history
persistence and the tab-completion candidate logic.
"""
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cli.shell import _init_readline, _load_history, _make_completer, _save_history
from tasker.workers.base import (
    Capability,
    ComputeLocation,
    LatencyClass,
    ProviderType,
    ToolProtocol,
    WorkerManifest,
)
from tasker.workers.registry import WorkerRegistry


def _worker(worker_id: str) -> WorkerManifest:
    return WorkerManifest(
        id=worker_id,
        provider=ProviderType.OLLAMA,
        model_id="test:latest",
        compute_location=ComputeLocation.LOCAL_HARDWARE,
        capabilities={Capability.TOOL_USE},
        tool_protocol=ToolProtocol.NATIVE,
        context_window=8192,
        cost_input=0.0,
        cost_output=0.0,
        ollama_usage_level=None,
        latency_class=LatencyClass.MEDIUM,
        available=True,
        requires_gpu=False,
        vram_mb=None,
    )


class TestMakeCompleter(unittest.TestCase):

    def setUp(self):
        self.registry = WorkerRegistry()
        self.registry.register(_worker("lfm2.5-local"))
        self.registry.register(_worker("claude-sonnet-4-6"))

    def _complete_all(self, completer, text):
        results = []
        state = 0
        while True:
            r = completer(text, state)
            if r is None:
                break
            results.append(r)
            state += 1
        return results

    def test_completes_slash_commands_at_start_of_line(self):
        completer = _make_completer(self.registry, _get_buffer=lambda: "/mo")
        results = self._complete_all(completer, "/mo")
        self.assertIn("/mode", results)
        self.assertIn("/model", results)
        self.assertIn("/models", results)

    def test_completes_mode_names_after_slash_mode_space(self):
        completer = _make_completer(self.registry, _get_buffer=lambda: "/mode ch")
        results = self._complete_all(completer, "ch")
        self.assertEqual(results, ["chat"])

    def test_completes_worker_ids_after_slash_model_space(self):
        completer = _make_completer(self.registry, _get_buffer=lambda: "/model lf")
        results = self._complete_all(completer, "lf")
        self.assertEqual(results, ["lfm2.5-local"])

    def test_completes_worker_ids_after_slash_resume_space(self):
        completer = _make_completer(self.registry, _get_buffer=lambda: "/resume cl")
        results = self._complete_all(completer, "cl")
        self.assertEqual(results, ["claude-sonnet-4-6"])

    def test_no_candidates_for_a_plain_chat_message(self):
        completer = _make_completer(self.registry, _get_buffer=lambda: "hello wor")
        results = self._complete_all(completer, "wor")
        self.assertEqual(results, [])

    def test_state_beyond_last_candidate_returns_none(self):
        completer = _make_completer(self.registry, _get_buffer=lambda: "/mo")
        self.assertIsNone(completer("/mo", 9999))


class TestHistoryPersistence(unittest.TestCase):

    def test_save_then_load_roundtrip(self):
        import readline

        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "history"
            readline.clear_history()
            readline.add_history("/mode chat")
            readline.add_history("Hello there")
            _save_history(path)
            self.assertTrue(path.exists())

            readline.clear_history()
            self.assertEqual(readline.get_current_history_length(), 0)
            _load_history(path)
            self.assertEqual(readline.get_current_history_length(), 2)
            self.assertEqual(readline.get_history_item(1), "/mode chat")

    def test_load_missing_file_is_a_silent_noop(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "does-not-exist"
            _load_history(path)   # must not raise

    def test_save_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "nested" / "dir" / "history"
            _save_history(path)
            self.assertTrue(path.parent.exists())

    def test_readline_none_is_a_no_op_everywhere(self):
        with mock.patch("cli.shell.readline", None):
            _load_history(Path("/nonexistent"))   # must not raise
            _save_history(Path("/nonexistent"))    # must not raise
            self.assertFalse(_init_readline(WorkerRegistry()))


class TestInitReadline(unittest.TestCase):

    def test_returns_true_and_configures_completer_when_available(self):
        registry = WorkerRegistry()
        with tempfile.TemporaryDirectory() as tmp:
            history_path = Path(tmp) / "history"
            with mock.patch("cli.shell.readline") as m_readline:
                result = _init_readline(registry, history_path)
        self.assertTrue(result)
        m_readline.set_completer_delims.assert_called_once_with(" \t\n")
        m_readline.set_completer.assert_called_once()
        m_readline.parse_and_bind.assert_called_once_with("tab: complete")

    def test_never_touches_real_home_directory_history_file(self):
        # Regression: _init_readline/_load_history must only touch the
        # path explicitly passed in, never Path.home() / ".tasker_history"
        # as a side effect of a test run.
        real_history = Path.home() / ".tasker_history"
        existed_before = real_history.exists()
        with tempfile.TemporaryDirectory() as tmp:
            _init_readline(WorkerRegistry(), Path(tmp) / "history")
        self.assertEqual(real_history.exists(), existed_before)


if __name__ == "__main__":
    unittest.main()
