"""
tasker.session.notifier
------------------------
NotifierBase ABC and implementations.

TerminalNotifier  -- countdown display + keypress handler.
LogNotifier       -- silent, writes to harness log only.
WebhookNotifier   -- user-configured POST endpoint.
DesktopNotifier   -- OS notification (cross-platform).
CompositeNotifier -- fires all registered notifiers.
See SDD Section 5.12.
"""
from __future__ import annotations

import asyncio
import json
import logging
import urllib.request
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class SessionEvent:
    """Carries a session lifecycle event to notifiers."""

    kind: str       # "paused" | "resumed" | "throttling" | "exhausted" | "status"
    timestamp: datetime
    message: str
    metadata: dict = field(default_factory=dict)

    @classmethod
    def paused(cls, message: str, **meta) -> SessionEvent:
        return cls(kind="paused", timestamp=datetime.now().astimezone(), message=message, metadata=meta)

    @classmethod
    def resumed(cls, message: str, **meta) -> SessionEvent:
        return cls(kind="resumed", timestamp=datetime.now().astimezone(), message=message, metadata=meta)

    @classmethod
    def throttling(cls, message: str, **meta) -> SessionEvent:
        return cls(kind="throttling", timestamp=datetime.now().astimezone(), message=message, metadata=meta)

    @classmethod
    def exhausted(cls, message: str, **meta) -> SessionEvent:
        return cls(kind="exhausted", timestamp=datetime.now().astimezone(), message=message, metadata=meta)


class NotifierBase(ABC):

    @abstractmethod
    async def send(self, event: SessionEvent) -> None:
        """Deliver a session lifecycle event to the user."""


class TerminalNotifier(NotifierBase):
    """Prints session events to stdout."""

    async def send(self, event: SessionEvent) -> None:
        ts = event.timestamp.strftime("%H:%M:%S")
        print(f"[{ts}] {event.kind.upper()}: {event.message}")


class LogNotifier(NotifierBase):
    """Writes events to the harness logger — silent to the user terminal."""

    def __init__(self, logger_name: str = "tasker.session") -> None:
        self._log = logging.getLogger(logger_name)

    async def send(self, event: SessionEvent) -> None:
        self._log.info(
            "[%s] %s: %s %s",
            event.timestamp.isoformat(),
            event.kind,
            event.message,
            event.metadata or "",
        )


class WebhookNotifier(NotifierBase):
    """POSTs event JSON to a user-configured URL via a thread-pool executor."""

    def __init__(self, url: str, timeout: float = 5.0) -> None:
        self._url = url
        self._timeout = timeout

    async def send(self, event: SessionEvent) -> None:
        payload = json.dumps({
            "kind": event.kind,
            "timestamp": event.timestamp.isoformat(),
            "message": event.message,
            "metadata": event.metadata,
        }).encode()
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._post, payload)

    def _post(self, payload: bytes) -> None:
        req = urllib.request.Request(
            self._url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self._timeout):
                pass
        except Exception:
            pass  # webhook failures must never block the session


class DesktopNotifier(NotifierBase):
    """OS desktop notification. Falls back to terminal print when plyer is absent."""

    async def send(self, event: SessionEvent) -> None:
        try:
            import plyer  # type: ignore[import]
            plyer.notification.notify(
                title=f"Tasker — {event.kind.upper()}",
                message=event.message,
                timeout=10,
            )
        except Exception:
            print(f"[DESKTOP] {event.kind.upper()}: {event.message}")


class CompositeNotifier(NotifierBase):
    """Fires all registered notifiers; individual failures are swallowed."""

    def __init__(self, notifiers: list[NotifierBase] | None = None) -> None:
        self._notifiers: list[NotifierBase] = list(notifiers) if notifiers else []

    def add(self, notifier: NotifierBase) -> None:
        self._notifiers.append(notifier)

    async def send(self, event: SessionEvent) -> None:
        for notifier in self._notifiers:
            try:
                await notifier.send(event)
            except Exception:
                pass
