"""SYS-06, 04-A V46: the owner's release tools (tools/release). Everything runs with throwaway keys in a temporary
folder outside the repository; no real key is made or read, and the passphrase prompts are replaced by the test."""

import importlib
import sys
from collections.abc import Iterator
from pathlib import Path
from types import ModuleType

import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from shelfsync.update import release_key
from shelfsync.update.manifest import parse_manifest, setup_asset_name, verify_and_parse
from tests.update_support import build_release, make_keys, sha

TOOLS = Path(__file__).resolve().parents[1] / "tools" / "release"
PASSPHRASE = "correct horse battery staple 42"


@pytest.fixture
def tools(monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, ModuleType]]:
    monkeypatch.syspath_prepend(str(TOOLS))
    loaded = {name: importlib.import_module(name) for name in ("keyfile", "keygen", "sign", "verify_setup")}
    yield loaded
    for name in loaded:
        sys.modules.pop(name, None)


def make_key_file(tools: dict[str, ModuleType], where: Path) -> tuple[Path, str]:
    path = where / "release-key.pem"
    public, _ = tools["keygen"].generate(path, PASSPHRASE)
    return path, public


# ---- keygen ---------------------------------------------------------------------------------------


def test_keygen_writes_an_encrypted_key_and_reports_the_public_key_and_the_algorithm(
    tools: dict[str, ModuleType], tmp_path: Path
) -> None:
    path = tmp_path / "key.pem"
    public, algorithm = tools["keygen"].generate(path, PASSPHRASE)
    pem = path.read_bytes()
    assert pem.startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----")
    assert len(public) == 64 and bytes.fromhex(public)
    assert "PBES2" in algorithm and "AES" in algorithm  # what 50.0.2 really wrote is printed, not assumed
    assert PASSPHRASE.encode() not in pem


def test_sign_loads_what_keygen_wrote_whatever_the_algorithm(tools: dict[str, ModuleType], tmp_path: Path) -> None:
    """V46: the encryption algorithm may change between cryptography versions; the file `keygen.py` made loads."""
    path, public = make_key_file(tools, tmp_path)
    key = tools["keyfile"].load_private_key(path, PASSPHRASE)
    assert tools["keyfile"].public_hex(key) == public
    for password in ("wrong passphrase 123456", ""):
        with pytest.raises(ValueError) as caught:
            tools["keyfile"].load_private_key(path, password)
        assert password not in str(caught.value) or password == ""


def test_the_algorithm_is_read_from_the_file_it_is_not_assumed(tools: dict[str, ModuleType], tmp_path: Path) -> None:
    key = Ed25519PrivateKey.generate()
    pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(PASSPHRASE.encode()),
    )
    description = tools["keyfile"].describe_encryption(pem)
    assert description.startswith("PBES2, ") and "AES-256-CBC" in description
    path = tmp_path / "k.pem"
    path.write_bytes(pem)
    assert tools["keyfile"].public_hex(tools["keyfile"].load_private_key(path, PASSPHRASE)) == tools[
        "keyfile"
    ].public_hex(key)


def test_a_key_of_another_kind_is_refused(tools: dict[str, ModuleType], tmp_path: Path) -> None:
    from cryptography.hazmat.primitives.asymmetric.ec import SECP256R1, generate_private_key

    path = tmp_path / "ec.pem"
    pem = generate_private_key(SECP256R1()).private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.BestAvailableEncryption(PASSPHRASE.encode()),
    )
    path.write_bytes(pem)
    with pytest.raises(ValueError, match="not Ed25519"):
        tools["keyfile"].load_private_key(path, PASSPHRASE)


def test_the_algorithm_description_never_guesses(tools: dict[str, ModuleType]) -> None:
    describe = tools["keyfile"].describe_encryption
    assert describe(b"garbage").startswith("unreadable")
    assert describe(b"-----BEGIN ENCRYPTED PRIVATE KEY-----\nAAAA\n-----END ENCRYPTED PRIVATE KEY-----\n").startswith(
        "unreadable"
    )


def test_keygen_refuses_a_short_passphrase_an_existing_file_and_a_place_in_the_repository(
    tools: dict[str, ModuleType], tmp_path: Path
) -> None:
    keygen = tools["keygen"]
    with pytest.raises(keygen.KeygenError):
        keygen.generate(tmp_path / "k.pem", "short")
    (tmp_path / "taken.pem").write_bytes(b"x")
    with pytest.raises(keygen.KeygenError):
        keygen.generate(tmp_path / "taken.pem", PASSPHRASE)
    assert (tmp_path / "taken.pem").read_bytes() == b"x"  # never overwritten
    with pytest.raises(keygen.KeygenError):
        keygen.generate(tools["keyfile"].REPO_ROOT / "docs" / "key.pem", PASSPHRASE)
    with pytest.raises(keygen.KeygenError):
        keygen.generate(tools["keyfile"].REPO_ROOT / "key.pem", PASSPHRASE)
    with pytest.raises(keygen.KeygenError):
        keygen.generate(tmp_path / "missing-folder" / "k.pem", PASSPHRASE)
    assert not (tools["keyfile"].REPO_ROOT / "docs" / "key.pem").exists()


def test_keygen_asks_twice_hides_the_input_and_prints_no_passphrase(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    prompts: list[str] = []
    answers = iter([PASSPHRASE, PASSPHRASE])
    monkeypatch.setattr(
        tools["keygen"].getpass, "getpass", lambda prompt="": (prompts.append(prompt), next(answers))[1]
    )
    assert tools["keygen"].main([str(tmp_path / "k.pem")]) == 0
    out = capsys.readouterr()
    assert len(prompts) == 2 and PASSPHRASE not in out.out + out.err and "Encryption used:" in out.out
    assert any(len(line) == 64 for line in out.out.splitlines())


def test_keygen_stops_when_the_two_passphrases_differ(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    answers = iter([PASSPHRASE, PASSPHRASE + "x"])
    monkeypatch.setattr(tools["keygen"].getpass, "getpass", lambda prompt="": next(answers))
    assert tools["keygen"].main([str(tmp_path / "k.pem")]) == 1
    assert not (tmp_path / "k.pem").exists()
    assert tools["keygen"].main([]) == 2


# ---- sign -----------------------------------------------------------------------------------------


def unsigned_manifest(tmp_path: Path, version: str = "0.1.2") -> Path:
    release = build_release(version, make_keys(1))
    path = tmp_path / "manifest.json"
    path.write_bytes(release.manifest_bytes)
    return path


def test_sign_writes_a_signature_the_app_accepts(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    key_path, public = make_key_file(tools, tmp_path)
    monkeypatch.setattr(release_key, "PUBLIC_KEY", bytes.fromhex(public))
    manifest = unsigned_manifest(tmp_path)
    written = tools["sign"].sign(manifest, key_path, PASSPHRASE)
    assert written.name == "manifest.json.sig" and len(written.read_bytes()) == 64
    assert verify_and_parse(manifest.read_bytes(), written.read_bytes()).version == "0.1.2"


def test_sign_refuses_to_overwrite_a_signature_and_a_wrong_passphrase_or_key(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    sign = tools["sign"]
    key_path, public = make_key_file(tools, tmp_path)
    manifest = unsigned_manifest(tmp_path)
    monkeypatch.setattr(release_key, "PUBLIC_KEY", None)
    with pytest.raises(sign.SignError):
        sign.sign(manifest, key_path, "wrong passphrase 123456")
    assert not (tmp_path / "manifest.json.sig").exists()
    monkeypatch.setattr(release_key, "PUBLIC_KEY", make_keys(5).public)  # another key is built into the app
    with pytest.raises(sign.SignError, match=r"not the one in release_key\.py"):
        sign.sign(manifest, key_path, PASSPHRASE)
    monkeypatch.setattr(release_key, "PUBLIC_KEY", bytes.fromhex(public))
    first = sign.sign(manifest, key_path, PASSPHRASE)
    before = first.read_bytes()
    with pytest.raises(sign.SignError, match="never overwrites"):
        sign.sign(manifest, key_path, PASSPHRASE)
    assert first.read_bytes() == before
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "manifest.json").write_bytes(manifest.read_bytes())
    with pytest.raises(sign.SignError, match="could not be read"):
        sign.sign(tmp_path / "other" / "manifest.json", tmp_path / "nokey.pem", PASSPHRASE)


def test_sign_refuses_a_file_that_is_not_a_manifest_and_an_oversize_one(
    tools: dict[str, ModuleType], tmp_path: Path
) -> None:
    sign = tools["sign"]
    key_path, _ = make_key_file(tools, tmp_path)
    junk = tmp_path / "junk" / "manifest.json"
    junk.parent.mkdir()
    junk.write_bytes(b'{"format": 1}')
    assert sign.main([str(junk), str(key_path)]) == 1
    big = tmp_path / "big" / "manifest.json"
    big.parent.mkdir()
    big.write_bytes(b" " * (3 * 1024 * 1024))
    with pytest.raises(sign.SignError):
        sign.sign(big, key_path, PASSPHRASE)


def test_sign_shows_what_it_signs_asks_and_never_prints_the_passphrase(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    sign = tools["sign"]
    key_path, public = make_key_file(tools, tmp_path)
    monkeypatch.setattr(release_key, "PUBLIC_KEY", bytes.fromhex(public))
    manifest = unsigned_manifest(tmp_path)
    parsed = parse_manifest(manifest.read_bytes())
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    assert sign.main([str(manifest), str(key_path)]) == 1  # "n": nothing is signed
    assert not (tmp_path / "manifest.json.sig").exists()
    shown = capsys.readouterr().out
    for expected in (
        parsed.version,
        parsed.tag,
        parsed.source_commit,
        parsed.built_at,
        *(e.sha256 for e in parsed.assets.values()),
    ):
        assert expected in shown
    monkeypatch.setattr("builtins.input", lambda prompt="": "y")
    monkeypatch.setattr(sign.getpass, "getpass", lambda prompt="": PASSPHRASE)
    assert sign.main([str(manifest), str(key_path)]) == 0
    out = capsys.readouterr()
    assert PASSPHRASE not in out.out + out.err and (tmp_path / "manifest.json.sig").is_file()
    assert sign.main([]) == 2


def test_sign_says_so_when_the_app_has_no_key_yet(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    key_path, _ = make_key_file(tools, tmp_path)
    monkeypatch.setattr(release_key, "PUBLIC_KEY", None)
    monkeypatch.setattr("builtins.input", lambda prompt="": "n")
    tools["sign"].main([str(unsigned_manifest(tmp_path)), str(key_path)])
    assert "no key yet" in capsys.readouterr().out
    assert tools["sign"].main([str(tmp_path / "missing.json"), str(key_path)]) == 1


# ---- verify_setup ---------------------------------------------------------------------------------


def signed_release(
    tmp_path: Path, tools: dict[str, ModuleType], monkeypatch: pytest.MonkeyPatch
) -> tuple[Path, Path, Path]:
    key_path, public = make_key_file(tools, tmp_path)
    monkeypatch.setattr(release_key, "PUBLIC_KEY", bytes.fromhex(public))
    release = build_release("0.1.2", make_keys(1))
    manifest = tmp_path / "manifest.json"
    manifest.write_bytes(release.manifest_bytes)
    signature = tools["sign"].sign(manifest, key_path, PASSPHRASE)
    setup = tmp_path / setup_asset_name("0.1.2")
    setup.write_bytes(release.setup_bytes)
    assert sha(release.setup_bytes) == parse_manifest(release.manifest_bytes).assets[setup.name].sha256
    return manifest, signature, setup


def test_verify_setup_passes_the_real_installer(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, signature, setup = signed_release(tmp_path, tools, monkeypatch)
    assert tools["verify_setup"].main([str(manifest), str(signature), str(setup)]) == 0
    assert "0.1.2" in capsys.readouterr().out


def test_verify_setup_fails_a_changed_installer_a_bad_signature_and_no_key(
    tools: dict[str, ModuleType], tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    manifest, signature, setup = signed_release(tmp_path, tools, monkeypatch)
    args = [str(manifest), str(signature), str(setup)]
    setup.write_bytes(setup.read_bytes() + b"!")  # same name, other bytes
    assert tools["verify_setup"].main(args) == 1 and "Do NOT run it" in capsys.readouterr().err
    setup.write_bytes(setup.read_bytes()[:-1])
    assert tools["verify_setup"].main(args) == 0
    signature.write_bytes(bytes(64))
    assert tools["verify_setup"].main(args) == 1 and "signature does not match" in capsys.readouterr().err
    monkeypatch.setattr(release_key, "PUBLIC_KEY", make_keys(6).public)  # a different key in the checkout
    signature.write_bytes(make_keys(7).sign(manifest.read_bytes()))  # a good signature, but by another key
    assert tools["verify_setup"].main(args) == 1
    monkeypatch.setattr(release_key, "PUBLIC_KEY", None)
    assert tools["verify_setup"].main(args) == 1 and "no public key yet" in capsys.readouterr().err
    assert tools["verify_setup"].main(args[:2]) == 2
    assert tools["verify_setup"].main([str(tmp_path / "nope"), str(signature), str(setup)]) == 1
