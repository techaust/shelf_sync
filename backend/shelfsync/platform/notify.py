"""Notifications behind a small interface. The real Windows toast adapter is M1a.4."""

import logging
from typing import Protocol

_log = logging.getLogger("shelfsync.notify")


class Notifier(Protocol):
    def notify(self, message: str) -> None:
        """Show the owner a message (a toast on Windows). Lines are separated by a newline."""
        ...


class FakeNotifier:
    """Records messages, for tests."""

    def __init__(self) -> None:
        self.messages: list[str] = []

    def notify(self, message: str) -> None:
        self.messages.append(message)


class LogNotifier:
    """Stand-in until the toast adapter exists: writes the message to the log."""

    def notify(self, message: str) -> None:
        _log.warning(message)
