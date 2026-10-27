"""SYS-05, 04-A V29: the toast adapter behind the Notifier interface, and windows-toasts only on Windows."""

import logging
import sys
import tomllib
from pathlib import Path

import pytest

from shelfsync import messages
from shelfsync.platform import notify
from shelfsync.platform.notify import FakeNotifier, LogNotifier, ToastNotifier, toast_text_fields

REPO = Path(__file__).parents[1]


def test_one_line_is_the_title_two_lines_are_title_and_body() -> None:
    """SYS-05: the first line is the toast's bold title."""
    assert toast_text_fields("Only a title") == ["Only a title"]
    assert toast_text_fields("Title\nBody") == ["Title", "Body"]


def test_more_than_three_lines_share_the_third_field() -> None:
    """SYS-05: a toast has three text lines."""
    assert toast_text_fields("a\nb\nc\nd") == ["a", "b", "c\nd"]


def test_blank_lines_are_dropped() -> None:
    """SYS-05."""
    assert toast_text_fields("a\n\n  \nb") == ["a", "b"]


def test_every_owner_facing_message_fits_a_toast() -> None:
    """SYS-05: the start-up notices reach real toasts as they are (13 section 3)."""
    for text in (messages.START_FAILED, messages.START_FAILED_MIGRATION, messages.ERR06_ALL_IN_USE):
        assert toast_text_fields(text) == [text]


def test_the_adapter_shows_the_message_and_logs_it(caplog: pytest.LogCaptureFixture) -> None:
    """SYS-05."""
    shown: list[list[str | None]] = []
    with caplog.at_level(logging.WARNING, logger="shelfsync.notify"):
        ToastNotifier(shown.append).notify(
            "Port 47615 is in use, so ShelfSync started on 47616.\nOpen it from the tray."
        )
    assert shown == [["Port 47615 is in use, so ShelfSync started on 47616.", "Open it from the tray."]]
    assert "started on 47616" in caplog.text


def test_a_toast_that_cant_be_shown_is_logged_not_raised(caplog: pytest.LogCaptureFixture) -> None:
    """SYS-05: Focus Assist, the notification service off, no desktop: the app carries on."""

    def refuse(fields: list[str | None]) -> None:
        raise OSError("secret-looking detail ck_" + "a" * 40)

    with caplog.at_level(logging.WARNING, logger="shelfsync.notify"):
        ToastNotifier(refuse).notify("hello")
    assert "A notification couldn't be shown (OSError)" in caplog.text
    assert "ck_" not in caplog.text  # nothing from the exception but its type


def test_the_default_notifier_is_the_toast_adapter_only_on_windows() -> None:
    """SYS-05: Linux CI keeps the fake or the log."""
    expected = ToastNotifier if sys.platform == "win32" else LogNotifier
    assert type(notify.default_notifier()) is expected
    assert not isinstance(notify.default_notifier(), FakeNotifier)


def test_v29_windows_toasts_carries_a_windows_marker_in_the_lock() -> None:
    """V29: ShelfSync's own list puts windows-toasts (and keyring) behind sys_platform == 'win32', so Linux CI
    installs none of the WinRT packages."""
    lock = tomllib.loads((REPO / "uv.lock").read_text(encoding="utf-8"))
    app = next(package for package in lock["package"] if package["name"] == "shelfsync")
    dependencies = {entry["name"]: entry for entry in app["dependencies"]}
    assert dependencies["windows-toasts"]["marker"] == "sys_platform == 'win32'"
    assert dependencies["keyring"]["marker"] == "sys_platform == 'win32'"
    assert "marker" not in dependencies["pystray"]  # on every platform: its backend is chosen when imported


def test_v29_the_pyproject_pins_windows_toasts_with_the_marker() -> None:
    """V29."""
    text = (REPO / "pyproject.toml").read_text(encoding="utf-8")
    assert "\"windows-toasts==1.3.1; sys_platform == 'win32'\"" in text
    assert '"pystray==0.19.5"' in text and '"Pillow==13.0.0"' in text


@pytest.mark.skipif(sys.platform == "win32", reason="the other platforms don't have windows-toasts")
def test_v29_windows_toasts_is_not_installed_off_windows() -> None:
    """V29: the marker kept it out, and `show_toast` fails (ImportError) instead of pretending."""
    with pytest.raises(ImportError):
        notify.show_toast(["x"])


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_v29_windows_toasts_imports_on_windows_and_a_toast_can_be_made() -> None:
    """V29: the package and its WinRT dependencies import here."""
    from windows_toasts import InteractableWindowsToaster, Toast

    toast = Toast(toast_text_fields("ShelfSync test notification\nSafe to ignore."))
    assert toast.text_fields == ["ShelfSync test notification", "Safe to ignore."]
    assert InteractableWindowsToaster("ShelfSync").notifierAUMID


@pytest.mark.windows
@pytest.mark.skipif(sys.platform != "win32", reason="Windows only")
def test_the_real_adapter_shows_one_toast_without_raising(caplog: pytest.LogCaptureFixture) -> None:
    """SYS-05 smoke test: one small toast appears on this PC ("ShelfSync test notification"); nothing is raised and
    nothing logs a failure. (Whether the owner sees it depends on Focus Assist; this checks the call goes through.)"""
    with caplog.at_level(logging.WARNING, logger="shelfsync.notify"):
        notify.ToastNotifier().notify("ShelfSync test notification\nSafe to ignore: a check of the toast adapter.")
    assert "couldn't be shown" not in caplog.text
