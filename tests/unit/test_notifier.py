"""
Unit tests -- Notifier implementations (tasker/session/notifier.py)
Phase 7 -- SDD Section 5.12
"""
import asyncio
import io
import logging
import sys
import types
import unittest
import unittest.mock
from datetime import datetime

from tasker.session.notifier import (
    CompositeNotifier,
    DesktopNotifier,
    LogNotifier,
    NotifierBase,
    SessionEvent,
    TerminalNotifier,
    WebhookNotifier,
)


# ------------------------------------------------------------------ #
# Helpers
# ------------------------------------------------------------------ #

def _event(kind: str = "paused", message: str = "test message") -> SessionEvent:
    return SessionEvent(kind=kind, timestamp=datetime.now().astimezone(), message=message)


class _RaisingNotifier(NotifierBase):
    async def send(self, event: SessionEvent) -> None:
        raise RuntimeError("intentional failure")


class _RecordingNotifier(NotifierBase):
    def __init__(self):
        self.received: list[SessionEvent] = []

    async def send(self, event: SessionEvent) -> None:
        self.received.append(event)


# ------------------------------------------------------------------ #
# SessionEvent
# ------------------------------------------------------------------ #

class TestSessionEvent(unittest.TestCase):

    def test_paused_factory(self):
        e = SessionEvent.paused("budget exhausted")
        self.assertEqual(e.kind, "paused")
        self.assertEqual(e.message, "budget exhausted")

    def test_resumed_factory(self):
        e = SessionEvent.resumed("back online")
        self.assertEqual(e.kind, "resumed")

    def test_throttling_factory(self):
        e = SessionEvent.throttling("90% consumed")
        self.assertEqual(e.kind, "throttling")

    def test_exhausted_factory(self):
        e = SessionEvent.exhausted("session ended")
        self.assertEqual(e.kind, "exhausted")

    def test_metadata_default_empty(self):
        e = SessionEvent.paused("msg")
        self.assertEqual(e.metadata, {})

    def test_metadata_passed_as_kwargs(self):
        e = SessionEvent.paused("msg", checkpoint_id="abc-123")
        self.assertEqual(e.metadata["checkpoint_id"], "abc-123")


# ------------------------------------------------------------------ #
# TerminalNotifier
# ------------------------------------------------------------------ #

class TestTerminalNotifier(unittest.IsolatedAsyncioTestCase):

    async def test_send_prints_to_stdout(self):
        notifier = TerminalNotifier()
        event = _event("paused", "session paused")
        with unittest.mock.patch("builtins.print") as mock_print:
            await notifier.send(event)
        mock_print.assert_called_once()
        call_arg = mock_print.call_args[0][0]
        self.assertIn("PAUSED", call_arg)
        self.assertIn("session paused", call_arg)

    async def test_send_includes_timestamp(self):
        notifier = TerminalNotifier()
        event = _event()
        with unittest.mock.patch("builtins.print") as mock_print:
            await notifier.send(event)
        call_arg = mock_print.call_args[0][0]
        self.assertIn(":", call_arg)   # HH:MM:SS contains colons


# ------------------------------------------------------------------ #
# LogNotifier
# ------------------------------------------------------------------ #

class TestLogNotifier(unittest.IsolatedAsyncioTestCase):

    async def test_send_calls_logger_info(self):
        notifier = LogNotifier("tasker.test")
        event = _event("throttling", "90% used")
        with unittest.mock.patch.object(notifier._log, "info") as mock_info:
            await notifier.send(event)
        mock_info.assert_called_once()
        args = mock_info.call_args[0]
        self.assertTrue(any("throttling" in str(a) for a in args))

    async def test_custom_logger_name(self):
        notifier = LogNotifier("custom.logger")
        self.assertEqual(notifier._log.name, "custom.logger")


# ------------------------------------------------------------------ #
# WebhookNotifier
# ------------------------------------------------------------------ #

class TestWebhookNotifier(unittest.IsolatedAsyncioTestCase):

    async def test_send_posts_json_payload(self):
        notifier = WebhookNotifier("http://example.com/hook", timeout=1.0)
        event = _event("paused", "checkpoint saved")

        with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = unittest.mock.Mock(return_value=False)
            await notifier.send(event)

        mock_urlopen.assert_called_once()
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_method(), "POST")
        self.assertIn(b"paused", req.data)
        self.assertIn(b"checkpoint saved", req.data)

    async def test_send_swallows_network_errors(self):
        notifier = WebhookNotifier("http://unreachable.invalid/hook", timeout=0.01)
        event = _event()
        # Must not raise even when urlopen raises
        with unittest.mock.patch("urllib.request.urlopen", side_effect=OSError("no route")):
            await notifier.send(event)   # no exception

    async def test_post_swallows_timeout(self):
        import socket
        notifier = WebhookNotifier("http://example.com/hook")
        with unittest.mock.patch("urllib.request.urlopen", side_effect=socket.timeout("timed out")):
            notifier._post(b'{"kind":"paused"}')   # no exception

    async def test_content_type_header(self):
        notifier = WebhookNotifier("http://example.com/hook")
        event = _event()
        with unittest.mock.patch("urllib.request.urlopen") as mock_urlopen:
            mock_urlopen.return_value.__enter__ = lambda s: s
            mock_urlopen.return_value.__exit__ = unittest.mock.Mock(return_value=False)
            await notifier.send(event)
        req = mock_urlopen.call_args[0][0]
        self.assertEqual(req.get_header("Content-type"), "application/json")


# ------------------------------------------------------------------ #
# DesktopNotifier
# ------------------------------------------------------------------ #

class TestDesktopNotifier(unittest.IsolatedAsyncioTestCase):

    async def test_calls_plyer_notify_when_available(self):
        mock_plyer = types.ModuleType("plyer")
        mock_notify = unittest.mock.MagicMock()
        mock_plyer.notification = types.SimpleNamespace(notify=mock_notify)

        notifier = DesktopNotifier()
        event = _event("paused", "session paused")

        with unittest.mock.patch.dict(sys.modules, {"plyer": mock_plyer}):
            await notifier.send(event)

        mock_notify.assert_called_once()
        call_kwargs = mock_notify.call_args[1]
        self.assertIn("PAUSED", call_kwargs.get("title", ""))
        self.assertEqual(call_kwargs.get("message"), "session paused")

    async def test_falls_back_to_print_when_plyer_absent(self):
        notifier = DesktopNotifier()
        event = _event("exhausted", "budget gone")

        # Remove plyer from sys.modules to simulate absence
        with unittest.mock.patch.dict(sys.modules, {"plyer": None}):
            with unittest.mock.patch("builtins.print") as mock_print:
                await notifier.send(event)

        mock_print.assert_called_once()
        call_arg = mock_print.call_args[0][0]
        self.assertIn("EXHAUSTED", call_arg)
        self.assertIn("budget gone", call_arg)

    async def test_falls_back_to_print_when_notify_raises(self):
        mock_plyer = types.ModuleType("plyer")
        mock_plyer.notification = types.SimpleNamespace(
            notify=unittest.mock.MagicMock(side_effect=RuntimeError("no display"))
        )
        notifier = DesktopNotifier()
        event = _event("paused", "paused")

        with unittest.mock.patch.dict(sys.modules, {"plyer": mock_plyer}):
            with unittest.mock.patch("builtins.print") as mock_print:
                await notifier.send(event)

        mock_print.assert_called_once()


# ------------------------------------------------------------------ #
# CompositeNotifier
# ------------------------------------------------------------------ #

class TestCompositeNotifier(unittest.IsolatedAsyncioTestCase):

    async def test_fires_all_registered_notifiers(self):
        n1 = _RecordingNotifier()
        n2 = _RecordingNotifier()
        composite = CompositeNotifier([n1, n2])
        event = _event()
        await composite.send(event)
        self.assertEqual(len(n1.received), 1)
        self.assertEqual(len(n2.received), 1)

    async def test_continues_after_one_raises(self):
        n1 = _RaisingNotifier()
        n2 = _RecordingNotifier()
        composite = CompositeNotifier([n1, n2])
        await composite.send(_event())        # must not raise
        self.assertEqual(len(n2.received), 1)  # n2 still received the event

    async def test_add_appends_notifier(self):
        composite = CompositeNotifier()
        n = _RecordingNotifier()
        composite.add(n)
        await composite.send(_event())
        self.assertEqual(len(n.received), 1)

    async def test_empty_composite_is_noop(self):
        composite = CompositeNotifier()
        await composite.send(_event())   # no exception, no output

    async def test_multiple_raises_all_swallowed(self):
        composite = CompositeNotifier([_RaisingNotifier(), _RaisingNotifier()])
        await composite.send(_event())   # both raise, both swallowed

    async def test_event_identity_preserved(self):
        n = _RecordingNotifier()
        composite = CompositeNotifier([n])
        event = _event("resumed", "back online")
        await composite.send(event)
        self.assertIs(n.received[0], event)


if __name__ == "__main__":
    unittest.main()
