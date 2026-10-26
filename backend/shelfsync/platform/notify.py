"""Notifications behind a small interface (SYS-05). `ToastNotifier` is the Windows toast adapter (windows-toasts);
`FakeNotifier` and `LogNotifier` are for tests, Linux CI and any run where a toast can't be shown."""

import logging
import sys
from collections.abc import Callable
from typing import Any, Protocol

_log = logging.getLogger("shelfsync.notify")

APP_NAME = "ShelfSync"


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
    """Writes the message to the log. Used where no toast can be shown."""

    def notify(self, message: str) -> None:
        _log.warning(message)


def toast_text_fields(message: str) -> list[str | None]:
    """The message as toast text: the first line is the bold title, the second the body, any further lines go
    together into the third (a toast has three text lines)."""
    lines = [line for line in message.split("\n") if line.strip()]
    if len(lines) <= 3:
        return list(lines)
    return [lines[0], lines[1], "\n".join(lines[2:])]


def _real_toaster() -> Any:
    """The windows-toasts toaster. `InteractableWindowsToaster` with no AUMID uses the one Windows already knows
    (Command Prompt's) and puts "ShelfSync" in the toast's attribution line. Registering ShelfSync's own
    AppUserModelID (so the toast carries ShelfSync's name and icon) is M1b (V14)."""
    from windows_toasts import InteractableWindowsToaster

    return InteractableWindowsToaster(APP_NAME)


class ToastNotifier:
    """Shows each message as a Windows toast, and also writes it to the log. It never raises: a toast that can't be
    shown (the service is off, Focus Assist, no desktop) is logged and the app carries on."""

    def __init__(self, toaster_factory: Callable[[], Any] | None = None) -> None:
        self._factory = toaster_factory or _real_toaster
        self._toaster: Any = None

    def notify(self, message: str) -> None:
        _log.warning(message)
        try:
            from windows_toasts import Toast

            if self._toaster is None:
                self._toaster = self._factory()
            toast = Toast(toast_text_fields(message))
            self._toaster.show_toast(toast)
        except Exception as error:
            # Not the message again, and nothing from the exception beyond its type
            _log.warning("A notification couldn't be shown (%s)", type(error).__name__)


def default_notifier() -> Notifier:
    """The toast adapter on Windows, the log elsewhere."""
    return ToastNotifier() if sys.platform == "win32" else LogNotifier()
