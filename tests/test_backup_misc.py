"""SET-05: `temporary_secret` (the passphrase's life in the redaction) and the smoke test's scrypt probe."""

import importlib.util
import subprocess
import sys
from pathlib import Path

import pytest

from shelfsync.secure.redact import (
    MASK,
    MIN_REGISTERED_LENGTH,
    clear_secrets,
    redact,
    register_secret,
    temporary_secret,
)

REPO = Path(__file__).resolve().parents[1]
PASSPHRASE = "correct horse battery staple"


def test_a_temporary_secret_is_masked_inside_the_block_and_forgotten_after() -> None:
    with temporary_secret(PASSPHRASE, minimum=12):
        assert redact(f"x {PASSPHRASE} y") == f"x {MASK} y"
    assert redact(f"x {PASSPHRASE} y") == f"x {PASSPHRASE} y"


def test_it_is_forgotten_when_the_block_raises() -> None:
    with pytest.raises(RuntimeError), temporary_secret(PASSPHRASE, minimum=12):
        raise RuntimeError("boom")
    assert redact(PASSPHRASE) == PASSPHRASE


def test_a_value_that_was_already_registered_stays_registered() -> None:
    register_secret(PASSPHRASE)
    with temporary_secret(PASSPHRASE, minimum=12):
        pass
    assert redact(PASSPHRASE) == MASK


def test_other_registered_values_are_untouched_by_a_temporary_one() -> None:
    kept = "a-stored-secret-value-1234"
    register_secret(kept)
    with temporary_secret(PASSPHRASE, minimum=12):
        assert redact(f"{kept} {PASSPHRASE}") == f"{MASK} {MASK}"
    assert redact(f"{kept} {PASSPHRASE}") == f"{MASK} {PASSPHRASE}"


def test_the_shortest_accepted_passphrase_is_masked_with_minimum_12_and_the_default_stays_16() -> None:
    twelve = "abcdefghijkl"
    with temporary_secret(twelve, minimum=12):
        assert redact(f"a {twelve} b") == f"a {MASK} b"
    with temporary_secret(twelve):  # the registry's own minimum: too short, so not registered
        assert redact(f"a {twelve} b") == f"a {twelve} b"
    assert MIN_REGISTERED_LENGTH == 16
    clear_secrets()


def test_the_smoke_probe_runs_the_decided_scrypt_call_and_prints_32() -> None:
    spec = importlib.util.spec_from_file_location("shelfsync_packaging_smoke3", REPO / "packaging" / "smoke.py")
    assert spec is not None and spec.loader is not None
    smoke = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(smoke)
    assert (
        "hashlib.scrypt(b'x', salt=b'0' * 16, n=2**17, r=8, p=1, maxmem=256 * 1024 * 1024, dklen=32)"
        in smoke.SCRYPT_PROBE
    )
    result = subprocess.run(
        [sys.executable, "-c", smoke.SCRYPT_PROBE], capture_output=True, text=True, timeout=120, check=False
    )
    assert (result.returncode, result.stdout.strip()) == (0, "32")
    text = (REPO / "packaging" / "smoke.py").read_text(encoding="utf-8")
    assert text.index('"-c", ICONS_PROBE') < text.index('"-c", SCRYPT_PROBE') < text.index("shelfsync-smoke-")
