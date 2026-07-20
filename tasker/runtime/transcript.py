"""
tasker.runtime.transcript
---------------------------
REPL chat rewind buffer (SDD 7.6a). Live-testing request (Roland): text
scrolls off the terminal during a long REPL session and is otherwise
gone. A Transcript keeps every prompt, response, and slash-command
("key event") in memory for the session, auto-writes them to a markdown
file on disk as they happen (so nothing is lost even if the process
crashes or the terminal is closed without /quit), and supports
re-printing recent exchanges via the REPL's /transcript command.

Deliberately not import-coupled to cli/shell.py or Textual -- this is
plain data plus file I/O, reusable by a future TUI HarnessPanel (8.5)
the same way tasker/runtime/dispatch.py is shared today.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

_DEFAULT_TRANSCRIPT_DIR = Path.home() / ".tasker" / "transcripts"


@dataclass
class TranscriptEntry:
    timestamp: datetime
    kind: str          # "user" | "assistant" | "event"
    mode: str
    text: str


def _entry_line(entry: TranscriptEntry) -> str:
    ts = entry.timestamp.strftime("%H:%M:%S")
    if entry.kind == "user":
        return f"**[{ts}] ({entry.mode}) You:** {entry.text}"
    if entry.kind == "assistant":
        return f"**[{ts}] ({entry.mode}) Tasker:** {entry.text}"
    return f"_[{ts}] ({entry.mode}) {entry.text}_"


def default_transcript_path(when: datetime | None = None) -> Path:
    when = when or datetime.now()
    return _DEFAULT_TRANSCRIPT_DIR / f"{when:%Y%m%d-%H%M%S}.md"


class Transcript:
    """
    In-memory session transcript, optionally mirrored to a markdown file
    on disk as entries are recorded (SDD 7.6a). *path* is created (with
    parent directories) and given a header the moment the Transcript is
    constructed, so the file exists on disk from session start, not only
    after the first exchange.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.entries: list[TranscriptEntry] = []
        self.path: Path | None = None
        if path is not None:
            try:
                path.parent.mkdir(parents=True, exist_ok=True)
                header = f"# Tasker REPL Transcript\n\nStarted: {datetime.now():%Y-%m-%d %H:%M:%S}\n\n"
                path.write_text(header, encoding="utf-8")
                self.path = path
            except OSError:
                # Degrade to in-memory-only rather than crash the REPL over
                # an unwritable home directory / full disk -- /transcript
                # still works for the rest of the session, it just won't
                # survive the process exiting.
                self.path = None

    def record(self, kind: str, mode: str, text: str) -> TranscriptEntry:
        entry = TranscriptEntry(timestamp=datetime.now(), kind=kind, mode=mode, text=text)
        self.entries.append(entry)
        if self.path is not None:
            try:
                with self.path.open("a", encoding="utf-8") as fh:
                    fh.write(_entry_line(entry) + "\n\n")
            except OSError:
                pass
        return entry

    def exchanges(self) -> list[list[TranscriptEntry]]:
        """
        Group entries into exchanges: each "user" entry starts a new
        group; everything logged after it (the assistant's reply, any
        event entries) belongs to that same exchange until the next
        "user" entry. Any entries before the first "user" entry (e.g. a
        /mode switch before the first message) form their own leading
        group.
        """
        groups: list[list[TranscriptEntry]] = []
        for entry in self.entries:
            if entry.kind == "user" or not groups:
                groups.append([entry])
            else:
                groups[-1].append(entry)
        return groups

    def render_exchanges(self, n: int | None = None) -> list[str]:
        """Render the last *n* exchanges (all of them if None) as display
        lines, one TranscriptEntry per line, oldest first."""
        groups = self.exchanges()
        if n is not None:
            groups = groups[-n:]
        lines: list[str] = []
        for group in groups:
            for entry in group:
                lines.append(_entry_line(entry))
        return lines
