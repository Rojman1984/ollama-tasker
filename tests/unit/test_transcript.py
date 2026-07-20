"""
Unit tests -- tasker/runtime/transcript.py (REPL chat rewind buffer,
SDD 7.6a). Live-testing request (Roland): text scrolls off screen during
a long REPL session and is otherwise gone.

Every test passes an explicit tmp path (or None) -- never touches the
real ~/.tasker/transcripts.
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from tasker.runtime.transcript import Transcript, default_transcript_path


class TestDefaultTranscriptPath(unittest.TestCase):

    def test_path_is_under_dot_tasker_transcripts(self):
        path = default_transcript_path(datetime(2026, 7, 20, 14, 22, 33))
        self.assertEqual(path.parent.name, "transcripts")
        self.assertEqual(path.parent.parent.name, ".tasker")

    def test_filename_is_timestamp_shaped(self):
        path = default_transcript_path(datetime(2026, 7, 20, 14, 22, 33))
        self.assertEqual(path.name, "20260720-142233.md")


class TestTranscriptInMemory(unittest.TestCase):
    """Transcript(None) -- in-memory only, no disk I/O at all."""

    def test_record_appends_entry(self):
        t = Transcript(None)
        t.record("user", "chat", "Hello")
        self.assertEqual(len(t.entries), 1)
        self.assertEqual(t.entries[0].kind, "user")
        self.assertEqual(t.entries[0].mode, "chat")
        self.assertEqual(t.entries[0].text, "Hello")

    def test_path_is_none(self):
        t = Transcript(None)
        self.assertIsNone(t.path)


class TestTranscriptExchanges(unittest.TestCase):

    def test_groups_user_with_following_entries(self):
        t = Transcript(None)
        t.record("user", "chat", "Hello")
        t.record("assistant", "chat", "Hi there")
        t.record("user", "chat", "How are you")
        t.record("assistant", "chat", "Doing well")
        groups = t.exchanges()
        self.assertEqual(len(groups), 2)
        self.assertEqual([e.text for e in groups[0]], ["Hello", "Hi there"])
        self.assertEqual([e.text for e in groups[1]], ["How are you", "Doing well"])

    def test_leading_events_before_first_user_form_own_group(self):
        t = Transcript(None)
        t.record("event", "chat", "/mode chat")
        t.record("user", "chat", "Hello")
        groups = t.exchanges()
        self.assertEqual(len(groups), 2)
        self.assertEqual(groups[0][0].kind, "event")
        self.assertEqual(groups[1][0].kind, "user")

    def test_event_between_user_and_assistant_stays_in_same_exchange(self):
        t = Transcript(None)
        t.record("user", "chat", "create a file")
        t.record("event", "chat", "unverified side-effect claim")
        t.record("assistant", "chat", "[unverified] ...")
        groups = t.exchanges()
        self.assertEqual(len(groups), 1)
        self.assertEqual(len(groups[0]), 3)

    def test_empty_transcript_has_no_exchanges(self):
        t = Transcript(None)
        self.assertEqual(t.exchanges(), [])


class TestRenderExchanges(unittest.TestCase):

    def test_full_session_when_n_is_none(self):
        t = Transcript(None)
        for i in range(5):
            t.record("user", "chat", f"msg {i}")
            t.record("assistant", "chat", f"reply {i}")
        lines = t.render_exchanges(None)
        self.assertEqual(len(lines), 10)
        self.assertIn("msg 0", lines[0])

    def test_last_n_exchanges(self):
        t = Transcript(None)
        for i in range(5):
            t.record("user", "chat", f"msg {i}")
            t.record("assistant", "chat", f"reply {i}")
        lines = t.render_exchanges(2)
        self.assertEqual(len(lines), 4)
        self.assertIn("msg 3", lines[0])
        self.assertIn("msg 4", lines[2])

    def test_n_larger_than_available_returns_everything(self):
        t = Transcript(None)
        t.record("user", "chat", "only message")
        lines = t.render_exchanges(50)
        self.assertEqual(len(lines), 1)

    def test_empty_transcript_renders_no_lines(self):
        t = Transcript(None)
        self.assertEqual(t.render_exchanges(None), [])

    def test_rendered_lines_include_timestamp_mode_and_role(self):
        t = Transcript(None)
        t.record("user", "cowork", "do the thing")
        lines = t.render_exchanges(None)
        self.assertIn("(cowork)", lines[0])
        self.assertIn("You:", lines[0])
        self.assertIn("do the thing", lines[0])


class TestTranscriptDiskPersistence(unittest.TestCase):

    def test_creates_file_with_header_immediately(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sub" / "transcript.md"
            Transcript(path)
            self.assertTrue(path.exists())
            content = path.read_text(encoding="utf-8")
            self.assertIn("Tasker REPL Transcript", content)

    def test_record_appends_to_disk(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            t = Transcript(path)
            t.record("user", "chat", "Hello")
            t.record("assistant", "chat", "Hi there")
            content = path.read_text(encoding="utf-8")
            self.assertIn("Hello", content)
            self.assertIn("Hi there", content)

    def test_nothing_lost_survives_reading_mid_session(self):
        # "auto-write as the session runs" -- content must be on disk
        # after each record(), not only at some later flush/close point.
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "transcript.md"
            t = Transcript(path)
            t.record("user", "chat", "first")
            mid_content = path.read_text(encoding="utf-8")
            self.assertIn("first", mid_content)
            t.record("user", "chat", "second")
            end_content = path.read_text(encoding="utf-8")
            self.assertIn("first", end_content)
            self.assertIn("second", end_content)

    def test_unwritable_directory_degrades_to_in_memory_only(self):
        # A path whose parent can't be created (e.g. a file sitting where
        # a directory is expected) must not crash the REPL.
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / "not-a-directory"
            blocker.write_text("x", encoding="utf-8")
            bad_path = blocker / "transcripts" / "transcript.md"
            t = Transcript(bad_path)
            self.assertIsNone(t.path)
            t.record("user", "chat", "still works in memory")  # must not raise
            self.assertEqual(len(t.entries), 1)


if __name__ == "__main__":
    unittest.main()
