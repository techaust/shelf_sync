"""Sign-in tickets and sessions (SYS-03, 06 section 2).

Both live in memory only (owner, 2026-10-27): a sign-in lasts until the browser or ShelfSync closes, nothing about
it is written to disk, and there is no idle timeout. Only the SHA-256 digest of each ticket and session id is held,
so the raw values exist nowhere but in the browser and the one response that created them.
"""

import hashlib
import re
import secrets
import threading
import time
from collections import OrderedDict
from collections.abc import Callable

TICKET_LIFETIME_SECONDS = 60.0
MAX_TICKETS = 32  # outstanding at once; the oldest is dropped
MAX_SESSIONS = 64  # open at once; the oldest is dropped
_MAX_PRESENTED_LENGTH = 256  # real values are 43 characters; anything longer is refused without being hashed

_URL_SAFE = re.compile(r"[A-Za-z0-9_-]+")


def _digest(value: str) -> bytes:
    return hashlib.sha256(value.encode("utf-8", "surrogatepass")).digest()


class SessionStore:
    """Tickets and sessions. Thread-safe. `clock` returns seconds and defaults to `time.monotonic`."""

    def __init__(self, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._lock = threading.Lock()
        self._tickets: OrderedDict[bytes, float] = OrderedDict()  # digest -> time issued
        self._sessions: OrderedDict[bytes, None] = OrderedDict()  # digest, oldest first

    def issue_ticket(self) -> str:
        """A new single-use ticket, valid while `now < issued + 60`."""
        ticket = secrets.token_urlsafe(32)
        now = self._clock()
        with self._lock:
            self._drop_expired(now)
            while len(self._tickets) >= MAX_TICKETS:
                self._tickets.popitem(last=False)
            self._tickets[_digest(ticket)] = now
        return ticket

    def redeem_ticket(self, ticket: str) -> str | None:
        """Use a ticket once. Returns the new session id, or None if the ticket is unknown, used or expired."""
        if not ticket or len(ticket) > _MAX_PRESENTED_LENGTH:
            return None
        key = _digest(ticket)
        now = self._clock()
        with self._lock:
            issued = self._tickets.pop(key, None)  # removed under the lock: of two racing callers only one gets it
            if issued is None or not now < issued + TICKET_LIFETIME_SECONDS:
                return None
            session_id = secrets.token_urlsafe(32)
            while len(self._sessions) >= MAX_SESSIONS:
                self._sessions.popitem(last=False)
            self._sessions[_digest(session_id)] = None
            return session_id

    def check_session(self, session_id: str) -> bool:
        if not session_id or len(session_id) > _MAX_PRESENTED_LENGTH:
            return False
        key = _digest(session_id)
        with self._lock:
            return key in self._sessions

    def end_all(self) -> None:
        """End every open session and cancel every ticket (Reset access token)."""
        with self._lock:
            self._tickets.clear()
            self._sessions.clear()

    def _drop_expired(self, now: float) -> None:
        expired = [key for key, issued in self._tickets.items() if not now < issued + TICKET_LIFETIME_SECONDS]
        for key in expired:
            del self._tickets[key]


def sign_in_url(port: int, ticket: str) -> str:
    """The address to open in the browser: `http://127.0.0.1:<port>/#t=<ticket>`.

    The launcher and the toast click build the address only through this function, so the install token (which is
    never in a URL) can't end up there by hand-building.
    """
    if not _URL_SAFE.fullmatch(ticket):
        raise ValueError("a ticket holds only letters, digits, - and _")
    return f"http://127.0.0.1:{int(port)}/#t={ticket}"
