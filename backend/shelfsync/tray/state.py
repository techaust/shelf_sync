"""What the tray icon shows (UI-TRAY). A small in-process state object: the tray watches it, other parts set it.

Nothing sets `paused` or `attention` yet except tests; Pause everything and the live attention state are M5.
"""

import enum
import threading
from collections.abc import Callable


class IconState(enum.Enum):
    NORMAL = "normal"
    PAUSED = "paused"
    ATTENTION = "attention"  # needs the owner; wins over paused


class TrayState:
    """Thread-safe. `subscribe` callbacks run in the thread that changed the state, after the lock is released."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._paused = False
        self._attention = False
        self._listeners: list[Callable[[], None]] = []

    @property
    def paused(self) -> bool:
        with self._lock:
            return self._paused

    @property
    def icon_state(self) -> IconState:
        with self._lock:
            if self._attention:
                return IconState.ATTENTION
            return IconState.PAUSED if self._paused else IconState.NORMAL

    def set_paused(self, paused: bool) -> None:
        self._set("_paused", paused)

    def set_attention(self, attention: bool) -> None:
        self._set("_attention", attention)

    def subscribe(self, listener: Callable[[], None]) -> None:
        with self._lock:
            self._listeners.append(listener)

    def _set(self, field: str, value: bool) -> None:
        with self._lock:
            if getattr(self, field) == value:
                return
            setattr(self, field, value)
            listeners = list(self._listeners)
        for listener in listeners:
            listener()
