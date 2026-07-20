"""
Unit tests -- cli/shell.py chat rewind buffer wiring (2026-07-20, part 3
addendum): /transcript command, the terminal pager, the stdout Tee, and
that the REPL records user/assistant/event entries and mentions the
transcript path in its startup banner.

Every _repl()-driving test here mocks default_transcript_path to a tmp
path (never None -- this file specifically wants to prove the file gets
written) or None, and always mocks _init_readline/_save_history, same
discipline as test_cli_shell.py/test_cli_shell_context.py -- never
touches the real ~/.tasker/transcripts or ~/.tasker_history.
"""
import io
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

from cli.shell import _Tee, _page_lines, _print_transcript, _repl
from tasker.runtime.transcript import Transcript


class TestTee(unittest.TestCase):

    def test_writes_to_all_streams(self):
        a, b = io.StringIO(), io.StringIO()
        tee = _Tee(a, b)
        tee.write("hello")
        self.assertEqual(a.getvalue(), "hello")
        self.assertEqual(b.getvalue(), "hello")

    def test_flush_flushes_all_streams(self):
        a, b = mock.Mock(), mock.Mock()
        _Tee(a, b).flush()
        a.flush.assert_called_once()
        b.flush.assert_called_once()


class TestPageLines(unittest.TestCase):

    def test_short_output_no_pause_prompt(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _page_lines(["a", "b", "c"], page_size=10, _input=lambda p: "")
        self.assertEqual(out.getvalue(), "a\nb\nc\n")

    def test_paginates_in_chunks_and_prompts_between(self):
        prompts = []

        def fake_input(prompt):
            prompts.append(prompt)
            return ""

        out = io.StringIO()
        with redirect_stdout(out):
            _page_lines([str(i) for i in range(5)], page_size=2, _input=fake_input)
        self.assertEqual(len(prompts), 2)   # 3 chunks -> 2 "more" prompts
        self.assertIn("more", prompts[0])

    def test_q_stops_paging_early(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _page_lines([str(i) for i in range(10)], page_size=2, _input=lambda p: "q")
        # Only the first chunk printed before "q" stopped it.
        self.assertEqual(out.getvalue().strip(), "0\n1".replace("\n", "\n").strip())

    def test_empty_lines_prints_nothing_no_prompt(self):
        out = io.StringIO()
        called = []
        with redirect_stdout(out):
            _page_lines([], page_size=10, _input=lambda p: called.append(p))
        self.assertEqual(out.getvalue(), "")
        self.assertEqual(called, [])

    def test_keyboard_interrupt_during_prompt_stops_cleanly(self):
        def raising_input(prompt):
            raise KeyboardInterrupt

        out = io.StringIO()
        with redirect_stdout(out):
            _page_lines([str(i) for i in range(5)], page_size=2, _input=raising_input)
        # Must not propagate -- just stops.


class TestPrintTranscript(unittest.TestCase):

    def test_empty_transcript_message(self):
        out = io.StringIO()
        with redirect_stdout(out):
            _print_transcript(Transcript(None), None)
        self.assertIn("transcript empty", out.getvalue())

    def test_prints_recorded_exchanges(self):
        t = Transcript(None)
        t.record("user", "chat", "Hello")
        t.record("assistant", "chat", "Hi!")
        out = io.StringIO()
        with mock.patch("cli.shell._page_lines") as m_page:
            _print_transcript(t, None)
        lines = m_page.call_args[0][0]
        self.assertEqual(len(lines), 2)
        self.assertIn("Hello", lines[0])

    def test_n_limits_to_recent_exchanges(self):
        t = Transcript(None)
        for i in range(3):
            t.record("user", "chat", f"msg{i}")
            t.record("assistant", "chat", f"reply{i}")
        with mock.patch("cli.shell._page_lines") as m_page:
            _print_transcript(t, 1)
        lines = m_page.call_args[0][0]
        self.assertEqual(len(lines), 2)
        self.assertIn("msg2", lines[0])


class TestReplTranscriptIntegration(unittest.TestCase):

    def _registry_with(self, worker_ids):
        registry = mock.Mock()
        registry.get = lambda wid: mock.Mock(id=wid) if wid in worker_ids else None
        registry.list_all = lambda: []
        return registry

    def _run_repl(self, inputs, tmp_path, initial_mode="chat", chat_reply="Hi there!"):
        registry = self._registry_with(["lfm2.5-local"])
        store = mock.Mock()
        out = io.StringIO()

        async def fake_run_chat_task(*args, **kwargs):
            print(chat_reply)

        async def fake_run_task(*args, **kwargs):
            print("task output")

        with mock.patch("builtins.input", side_effect=inputs + ["/quit"]), \
             mock.patch("cli.shell._run_chat_task", side_effect=fake_run_chat_task), \
             mock.patch("cli.shell._run_task", side_effect=fake_run_task), \
             mock.patch("cli.shell._init_readline"), \
             mock.patch("cli.shell.default_transcript_path", return_value=tmp_path), \
             mock.patch("cli.shell._save_history"), \
             redirect_stdout(out):
            _repl(registry, store, initial_mode=initial_mode)
        return out.getvalue()

    def test_banner_mentions_transcript_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            output = self._run_repl([], path)
        self.assertIn("Transcript:", output)
        self.assertIn(str(path), output)

    def test_banner_omits_transcript_line_when_disk_unavailable(self):
        output = self._run_repl([], None)
        self.assertNotIn("Transcript:", output)

    def test_chat_exchange_recorded_and_written_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            self._run_repl(["Hello"], path, chat_reply="Hi there!")
            content = path.read_text(encoding="utf-8")
        self.assertIn("Hello", content)
        self.assertIn("Hi there!", content)

    def test_slash_command_recorded_as_event(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            self._run_repl(["/status"], path)
            content = path.read_text(encoding="utf-8")
        self.assertIn("/status", content)

    def test_transcript_command_reprints_prior_exchange(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            output = self._run_repl(["Hello", "/transcript"], path, chat_reply="Hi there!")
        self.assertIn("Hi there!", output)

    def test_transcript_command_accepts_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            output = self._run_repl(["Hello", "/transcript 1"], path, chat_reply="Hi there!")
        self.assertIn("Hi there!", output)

    def test_transcript_command_rejects_bad_n(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            output = self._run_repl(["/transcript abc"], path)
        self.assertIn("Usage: /transcript [n]", output)

    def test_non_chat_mode_exchange_also_recorded(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            self._run_repl(["do a code thing"], path, initial_mode="code")
            content = path.read_text(encoding="utf-8")
        self.assertIn("do a code thing", content)
        self.assertIn("task output", content)


if __name__ == "__main__":
    unittest.main()
