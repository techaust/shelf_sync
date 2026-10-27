"""SYS-03: the shell only opens ShelfSync's own address (a parsed check, not a prefix match), and only its own folder
through the shell's open."""

from pathlib import Path

import pytest

from shelfsync.platform.shell import FakeShell, ShellError, WindowsShell

GOOD = [
    "http://127.0.0.1:47615/#t=abc_DEF-123",
    "http://127.0.0.1:47624/",
    "http://127.0.0.1:1024/#t=x",
]
BAD = [
    "http://127.0.0.1:1@evil.example/",  # starts with the right text; its host is evil.example
    "http://127.0.0.1:47615@evil.example/#t=x",
    "http://127.0.0.1@evil.example:47615/",
    "http://user:pw@127.0.0.1:47615/",
    "http://:pw@127.0.0.1:47615/",
    "http://127.0.0.1:47615:80/",
    "http://127.0.0.1:/",
    "http://127.0.0.1/",  # no port
    "http://127.0.0.1:abc/",
    "http://127.0.0.1:99999/",
    "https://127.0.0.1:47615/",
    "http://localhost:47615/",
    "http://127.0.0.1.evil.example:47615/",
    "http://127.0.0.2:47615/",
    "http://[::1]:47615/",
    r"http://127.0.0.1:47615\@evil.example/",
    "ftp://127.0.0.1:47615/",
    "file:///C:/Windows/System32/calc.exe",
    "calc.exe",
    "",
    "//127.0.0.1:47615/",
    " http://127.0.0.1:47615/",
    "http://127.0.0.1:47615/\n",
    "http://127.0.0.1:47615/\t#t=x",
]


@pytest.mark.parametrize("url", GOOD)
def test_shelfsyncs_own_address_is_accepted(url: str) -> None:
    """SYS-03."""
    shell = FakeShell()
    shell.open_url(url)
    assert shell.urls == [url]


@pytest.mark.parametrize("url", BAD)
def test_anything_else_is_refused_by_the_fake_and_the_real_shell(url: str) -> None:
    """SYS-03 (review 8): scheme http, host exactly 127.0.0.1, a whole port, no user info."""
    with pytest.raises(ShellError):
        FakeShell().open_url(url)
    with pytest.raises(ShellError, match="own address"):  # refused before Windows is asked, on any platform
        WindowsShell().open_url(url)


def test_a_refused_address_is_not_in_the_error_message() -> None:
    """LOG-01: the address may hold a ticket; the error never repeats it."""
    with pytest.raises(ShellError) as error:
        FakeShell().open_url("http://127.0.0.1:1@evil.example/#t=SECRETTICKET")
    assert "SECRETTICKET" not in str(error.value) and "evil" not in str(error.value)


def test_the_fake_records_folders() -> None:
    """UI-TRAY."""
    shell = FakeShell()
    shell.open_folder(Path("logs"))
    assert shell.folders == [Path("logs")]
