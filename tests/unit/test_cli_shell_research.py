"""
Unit tests -- cli/shell.py RESEARCH mode no-backend announcement (SDD
5.1a). Live bug: research mode fabricated content with zero tool calls;
part of the fix is announcing the missing search backend up front rather
than silently producing fabricated (now honesty-guard-flagged) output.
"""
import io
import unittest
from contextlib import redirect_stdout
from datetime import datetime
from unittest import mock

from cli.shell import _repl, _warn_if_research_ungrounded
from tasker.session.budget import OllamaSessionBudget
from tasker.session.manager import SessionState
from tasker.workers.base import OllamaPlan


class TestWarnIfResearchUngrounded(unittest.TestCase):

    def test_warns_when_research_and_no_key(self):
        out = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True), redirect_stdout(out):
            _warn_if_research_ungrounded("research")
        self.assertIn("no search backend configured", out.getvalue())
        self.assertIn("BRAVE_API_KEY", out.getvalue())

    def test_silent_when_research_and_key_set(self):
        out = io.StringIO()
        with mock.patch.dict("os.environ", {"BRAVE_API_KEY": "key"}), redirect_stdout(out):
            _warn_if_research_ungrounded("research")
        self.assertEqual(out.getvalue(), "")

    def test_silent_for_other_modes_regardless_of_key(self):
        out = io.StringIO()
        with mock.patch.dict("os.environ", {}, clear=True), redirect_stdout(out):
            _warn_if_research_ungrounded("chat")
        self.assertEqual(out.getvalue(), "")


class TestReplResearchModeWarning(unittest.TestCase):

    def _registry_with(self, worker_ids):
        registry = mock.Mock()
        registry.get = lambda wid: mock.Mock(id=wid) if wid in worker_ids else None
        registry.list_all = lambda: []
        return registry

    def _fake_pipeline(self):
        budget = OllamaSessionBudget(plan=OllamaPlan.PRO, window_start=datetime.now().astimezone())
        session_mgr = mock.Mock()
        session_mgr.state = SessionState.RUNNING
        return ("tier1_tasker", mock.Mock(), budget, session_mgr, mock.Mock(), mock.Mock(), mock.Mock())

    def _run_repl(self, inputs, initial_mode="chat", env=None):
        registry = self._registry_with([])
        store = mock.Mock()
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=inputs + ["/quit"]), \
             mock.patch("cli.shell._run_chat_task"), \
             mock.patch("cli.shell._run_task"), \
             mock.patch("cli.shell._build_pipeline", return_value=self._fake_pipeline()), \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=None), \
             mock.patch("cli.shell._save_history"), \
             mock.patch.dict("os.environ", env or {}, clear=True), \
             redirect_stdout(out):
            _repl(registry, store, initial_mode=initial_mode)
        return out.getvalue()

    def test_mode_research_command_warns_without_key(self):
        output = self._run_repl(["/mode research"])
        self.assertIn("no search backend configured", output)

    def test_mode_research_command_silent_with_key(self):
        output = self._run_repl(["/mode research"], env={"BRAVE_API_KEY": "key"})
        self.assertNotIn("no search backend configured", output)

    def test_starting_directly_in_research_mode_warns_at_startup(self):
        output = self._run_repl([], initial_mode="research")
        self.assertIn("no search backend configured", output)

    def test_switching_away_from_research_does_not_warn(self):
        output = self._run_repl(["/mode chat"], initial_mode="chat")
        self.assertNotIn("no search backend configured", output)


if __name__ == "__main__":
    unittest.main()
