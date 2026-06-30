"""
tasker.session.notifier
------------------------
NotifierBase ABC and implementations.

TerminalNotifier -- countdown display + keypress handler.
LogNotifier      -- silent, writes to harness log only.
WebhookNotifier  -- user-configured POST endpoint.
DesktopNotifier  -- OS notification (cross-platform).
CompositeNotifier-- fires all registered notifiers.
See SDD Section 5.12.
"""
from __future__ import annotations
from abc import ABC, abstractmethod

# TODO Phase 2
#
# class NotifierBase(ABC):
#     @abstractmethod
#     async def send(self, event) -> None: ...