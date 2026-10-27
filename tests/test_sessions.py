"""SYS-03: tickets and sessions (single use, 60 seconds, capped, in memory only)."""

import threading

import pytest

from shelfsync.secure.sessions import MAX_SESSIONS, MAX_TICKETS, SessionStore, sign_in_url
from tests.support import FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def store(clock: FakeClock) -> SessionStore:
    return SessionStore(clock)


def test_redeem_at_59_999_seconds_is_ok_and_at_60_is_refused(store: SessionStore, clock: FakeClock) -> None:
    """SYS-03: valid while now < issued + 60."""
    ticket = store.issue_ticket()
    clock.advance(59.999)
    assert store.redeem_ticket(ticket) is not None
    late = store.issue_ticket()
    clock.advance(60.0)
    assert store.redeem_ticket(late) is None


def test_a_ticket_is_single_use(store: SessionStore) -> None:
    """SYS-03: a second redeem is refused."""
    ticket = store.issue_ticket()
    assert store.redeem_ticket(ticket) is not None
    assert store.redeem_ticket(ticket) is None


def test_a_redeemed_ticket_makes_a_session_that_checks_out(store: SessionStore) -> None:
    """SYS-03: the session id is valid, an invented one is not."""
    session_id = store.redeem_ticket(store.issue_ticket())
    assert session_id is not None
    assert store.check_session(session_id)
    assert not store.check_session(session_id + "x")


@pytest.mark.parametrize("bad", ["", "nope", "x" * 10_240, "é" * 40, "\ud800", "a b"], ids=lambda v: repr(v)[:12])
def test_unknown_empty_and_huge_tickets_and_sessions_are_refused(store: SessionStore, bad: str) -> None:
    """SYS-03: nothing odd is accepted, and nothing odd raises."""
    assert store.redeem_ticket(bad) is None
    assert store.check_session(bad) is False


def test_two_threads_redeeming_the_same_ticket_one_wins(store: SessionStore) -> None:
    """SYS-03: of two threads redeeming the same ticket at once, exactly one gets it.

    This checks the contract, not the lock: under CPython's GIL `OrderedDict.pop` is atomic by itself, so this test
    would still pass if the lock were removed. The lock is there so that the check of the time and the removal stay
    one step on any interpreter.
    """
    for _ in range(300):
        ticket = store.issue_ticket()
        barrier = threading.Barrier(2)
        results: list[str | None] = []

        def redeem(
            ticket: str = ticket, barrier: threading.Barrier = barrier, results: list[str | None] = results
        ) -> None:
            barrier.wait()
            results.append(store.redeem_ticket(ticket))

        threads = [threading.Thread(target=redeem) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()
        assert sum(result is not None for result in results) == 1


def test_at_most_32_tickets_are_outstanding_and_the_oldest_is_dropped(store: SessionStore) -> None:
    """SYS-03: the cap on tickets."""
    tickets = [store.issue_ticket() for _ in range(MAX_TICKETS + 1)]
    assert store.redeem_ticket(tickets[0]) is None  # dropped
    assert all(store.redeem_ticket(ticket) is not None for ticket in tickets[1:])


def test_at_most_64_sessions_are_open_and_the_oldest_is_dropped(store: SessionStore) -> None:
    """SYS-03: the cap on sessions."""
    sessions = [store.redeem_ticket(store.issue_ticket()) for _ in range(MAX_SESSIONS + 1)]
    assert None not in sessions
    assert not store.check_session(sessions[0] or "")
    assert all(store.check_session(session or "") for session in sessions[1:])


def test_expired_tickets_are_swept_when_a_new_one_is_issued(store: SessionStore, clock: FakeClock) -> None:
    """SYS-03: expired tickets don't count against the cap."""
    old = [store.issue_ticket() for _ in range(MAX_TICKETS)]
    clock.advance(61)
    fresh = store.issue_ticket()
    assert all(store.redeem_ticket(ticket) is None for ticket in old)
    assert store.redeem_ticket(fresh) is not None


def test_end_all_refuses_old_sessions_and_tickets(store: SessionStore) -> None:
    """SET-06: Reset access token ends every open session and cancels every ticket."""
    ticket = store.issue_ticket()
    session_id = store.redeem_ticket(store.issue_ticket())
    assert session_id is not None
    store.end_all()
    assert not store.check_session(session_id)
    assert store.redeem_ticket(ticket) is None


def test_only_digests_are_held(store: SessionStore) -> None:
    """SYS-03: the raw ticket and session values are not kept in memory by the store."""
    ticket = store.issue_ticket()
    session_id = store.redeem_ticket(store.issue_ticket())
    assert session_id is not None
    held = repr(vars(store))
    assert ticket not in held
    assert session_id not in held


def test_sign_in_url_holds_the_ticket_and_never_the_token() -> None:
    """SYS-03: http://127.0.0.1:<port>/#t=<ticket>."""
    url = sign_in_url(47615, "abc_DEF-123")
    assert url == "http://127.0.0.1:47615/#t=abc_DEF-123"


@pytest.mark.parametrize("ticket", ["", "a b", "a/b", "a#b", "a?b", "é", "a\nb"])
def test_sign_in_url_refuses_a_ticket_that_isnt_url_safe(ticket: str) -> None:
    """SYS-03: nothing but a real ticket can be put in the address."""
    with pytest.raises(ValueError):
        sign_in_url(47615, ticket)
