"""SET-06: Reset access token against a ticket request that is already past the token check."""

import threading

import pytest

from shelfsync.secure.sessions import SessionStore
from tests.support import WRITE_HEADERS, Harness, make_harness


@pytest.fixture
def harness() -> Harness:
    return make_harness()


def test_a_reset_cannot_fall_between_the_token_check_and_the_ticket(
    harness: Harness, monkeypatch: pytest.MonkeyPatch
) -> None:
    """SET-06: a leaked old token that was valid when checked must not end up with a ticket that outlives the reset.

    The ticket request is slowed down inside `issue_ticket` (after the token check) until a reset has had time to
    finish on another thread. Either the request gets no ticket, or the ticket it gets is refused at /api/session.
    """
    old_token = harness.token
    admin = harness.signed_in_client()  # signed in before issue_ticket is patched
    issue_started = threading.Event()
    reset_finished = threading.Event()
    real_issue = SessionStore.issue_ticket

    def slow_issue(self: SessionStore) -> str:
        issue_started.set()
        reset_finished.wait(timeout=0.5)  # with the lock the reset waits for us, so this times out
        return real_issue(self)

    monkeypatch.setattr(SessionStore, "issue_ticket", slow_issue)
    outcome: dict[str, int | str | None] = {}

    def ask_for_ticket() -> None:
        response = harness.client().post("/api/session/ticket", headers={"Authorization": f"Bearer {old_token}"})
        outcome["status"] = response.status_code
        outcome["ticket"] = response.json().get("ticket") if response.status_code == 200 else None

    def reset() -> None:
        issue_started.wait(timeout=5)
        admin.post("/api/session/reset-token", headers=WRITE_HEADERS)
        reset_finished.set()

    threads = [threading.Thread(target=ask_for_ticket), threading.Thread(target=reset)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=10)
    assert harness.token != old_token  # the reset did happen
    ticket = outcome["ticket"]
    if ticket is not None:
        response = harness.client().post("/api/session", json={"ticket": ticket}, headers=WRITE_HEADERS)
        assert response.status_code == 401
    else:
        assert outcome["status"] == 401
