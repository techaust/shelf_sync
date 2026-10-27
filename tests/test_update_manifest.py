"""SYS-06, 06 section 6: the signed manifest. The signature is raw (64 bytes), checked before the JSON is parsed, and
the key is the module constant `release_key.PUBLIC_KEY` and nothing else."""

import json
import os
from pathlib import Path

import pytest
from hypothesis import HealthCheck, given, settings
from hypothesis import strategies as st

from shelfsync.update import release_key
from shelfsync.update.manifest import (
    MAX_MANIFEST_BYTES,
    FileEntry,
    ManifestError,
    canonical_bytes,
    check_acceptable,
    check_is_version,
    is_safe_relative_path,
    main,
    make_manifest,
    parse_files_txt,
    parse_manifest,
    setup_asset_name,
    verify_and_parse,
    verify_signature,
    zip_asset_name,
)
from shelfsync.update.versions import VersionError, is_newer, is_valid_version, parse_version, tag_for
from tests.update_support import BUILT_AT, COMMIT, build_release, entries, make_keys, sha, use_key

KEYS = make_keys(1)
OTHER = make_keys(2)


def code_of(call: object) -> str:
    assert callable(call)
    with pytest.raises(ManifestError) as caught:
        call()
    return caught.value.code


def manifest_document(version: str = "0.0.2") -> dict[str, object]:
    release = build_release(version, KEYS)
    loaded = json.loads(release.manifest_bytes)
    assert isinstance(loaded, dict)
    return loaded


def sign_document(document: dict[str, object]) -> tuple[bytes, bytes]:
    data = canonical_bytes(document)
    return data, KEYS.sign(data)


# ---- versions ----------------------------------------------------------------------------------------------------


@pytest.mark.parametrize("text", ["0.0.1", "1.2.3", "10.20.30", "0.0.0"])
def test_a_strict_version_parses(text: str) -> None:
    assert is_valid_version(text)
    assert tag_for(text) == f"v{text}"


@pytest.mark.parametrize(
    "text",
    [
        "1.2",
        "1.2.3.4",
        "01.2.3",
        "1.02.3",
        "1.2.03",
        "v1.2.3",
        "1.2.3-rc1",
        "1.2.3+b",
        " 1.2.3",
        "1.2.3\n",
        "-1.2.3",
        "١.٢.٣",
        "",
        "1..3",
    ],
)
def test_anything_but_x_y_z_is_refused(text: str) -> None:
    assert not is_valid_version(text)
    with pytest.raises(VersionError):
        parse_version(text)


def test_a_version_that_is_not_text_is_refused() -> None:
    with pytest.raises(VersionError):
        parse_version(3)


def test_versions_compare_as_integers_not_text() -> None:
    assert is_newer("0.10.0", "0.9.0")
    assert is_newer("1.0.0", "0.99.99")
    assert not is_newer("0.0.2", "0.0.2")
    assert not is_newer("0.0.1", "0.0.2")


# ---- the signature -------------------------------------------------------------------------------------------------


def test_a_manifest_signed_by_the_key_is_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    release = build_release("0.0.2", KEYS)
    manifest = verify_and_parse(release.manifest_bytes, release.signature)
    assert manifest.version == "0.0.2" and manifest.tag == "v0.0.2" and manifest.source_commit == COMMIT


def test_an_unsigned_manifest_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    release = build_release("0.0.2", KEYS, sign=False)  # 64 zero bytes: the right length, the wrong bytes
    assert code_of(lambda: verify_and_parse(release.manifest_bytes, release.signature)) == "bad_signature"
    assert code_of(lambda: verify_and_parse(release.manifest_bytes, b"")) == "bad_signature"


def test_a_signature_by_another_key_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    release = build_release("0.0.2", OTHER)
    assert code_of(lambda: verify_and_parse(release.manifest_bytes, release.signature)) == "bad_signature"


def test_tampered_bytes_are_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    release = build_release("0.0.2", KEYS)
    tampered = release.manifest_bytes.replace(b"0.0.2", b"9.9.9", 1)
    assert code_of(lambda: verify_and_parse(tampered, release.signature)) == "bad_signature"
    assert code_of(lambda: verify_and_parse(release.manifest_bytes + b"\n", release.signature)) == "bad_signature"


@pytest.mark.parametrize("length", [0, 1, 63, 65, 128])
def test_a_signature_that_is_not_64_bytes_is_refused(monkeypatch: pytest.MonkeyPatch, length: int) -> None:
    use_key(monkeypatch, KEYS)
    release = build_release("0.0.2", KEYS)
    assert (
        code_of(lambda: verify_and_parse(release.manifest_bytes, (release.signature * 3)[:length])) == "bad_signature"
    )


def test_an_armoured_or_hex_signature_is_not_accepted(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    release = build_release("0.0.2", KEYS)
    assert (
        code_of(lambda: verify_and_parse(release.manifest_bytes, release.signature.hex().encode())) == "bad_signature"
    )


def test_the_signature_is_checked_before_the_json_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    """A malformed manifest with a bad signature reports the signature, never the malformation."""
    use_key(monkeypatch, KEYS)
    assert code_of(lambda: verify_and_parse(b"{ this is not json", b"\x00" * 64)) == "bad_signature"
    assert code_of(lambda: verify_and_parse(b"\xff\xfe\x00", b"\x00" * 64)) == "bad_signature"
    # and signed garbage is a format problem, found only after the signature passed
    garbage = b"{ not json"
    assert code_of(lambda: verify_and_parse(garbage, KEYS.sign(garbage))) == "bad_format"


def test_a_validly_signed_manifest_with_bad_content_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    document = manifest_document()
    document["files"] = {"../evil.dll": {"size": 1, "sha256": "0" * 64}}
    assert code_of(lambda: verify_and_parse(*sign_document(document))) == "bad_path"


def test_no_key_in_the_build_means_nothing_verifies(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, None)
    release = build_release("0.0.2", KEYS)
    assert release_key.PUBLIC_KEY is None
    assert code_of(lambda: verify_and_parse(release.manifest_bytes, release.signature)) == "no_key"


def test_a_key_that_is_not_32_bytes_refuses_everything(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(release_key, "PUBLIC_KEY", b"\x01" * 31)
    release = build_release("0.0.2", KEYS)
    assert code_of(lambda: verify_and_parse(release.manifest_bytes, release.signature)) == "bad_signature"


def test_no_setting_environment_variable_or_file_can_change_the_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """Verification reads the module constant at the moment of use. Other keys offered through the environment, the
    working directory or the data folder are ignored."""
    use_key(monkeypatch, KEYS)
    for name in ("SHELFSYNC_PUBLIC_KEY", "SHELFSYNC_RELEASE_KEY", "PUBLIC_KEY", "SHELFSYNC_DATA_DIR"):
        monkeypatch.setenv(name, OTHER.public.hex())
    monkeypatch.chdir(tmp_path)
    (tmp_path / "release_key.py").write_text(f"PUBLIC_KEY = bytes.fromhex('{OTHER.public.hex()}')", encoding="utf-8")
    (tmp_path / "public_key.pem").write_bytes(OTHER.public)
    release = build_release("0.0.2", OTHER)  # signed by the key those channels offer
    assert code_of(lambda: verify_and_parse(release.manifest_bytes, release.signature)) == "bad_signature"
    good = build_release("0.0.2", KEYS)
    assert verify_and_parse(good.manifest_bytes, good.signature).version == "0.0.2"


def test_the_key_constant_is_the_only_thing_the_verifier_reads() -> None:
    """No function in the manifest module accepts a key, and the source mentions no environment or file for one."""
    import inspect

    from shelfsync.update import manifest as module

    assert "environ" not in inspect.getsource(module)
    assert list(inspect.signature(verify_signature).parameters) == ["manifest_bytes", "signature"]
    assert list(inspect.signature(verify_and_parse).parameters) == ["manifest_bytes", "signature"]


@settings(max_examples=60, deadline=None, suppress_health_check=[HealthCheck.function_scoped_fixture])
@given(data=st.data())
def test_any_single_bit_flip_in_the_manifest_or_the_signature_is_refused(data: st.DataObject) -> None:
    keys = make_keys(1)
    release = build_release("0.0.2", keys)
    from shelfsync.update import release_key as key_module

    original = key_module.PUBLIC_KEY
    key_module.PUBLIC_KEY = keys.public
    try:
        in_manifest = data.draw(st.booleans())
        target = bytearray(release.manifest_bytes if in_manifest else release.signature)
        bit = data.draw(st.integers(min_value=0, max_value=len(target) * 8 - 1))
        target[bit // 8] ^= 1 << (bit % 8)
        manifest_bytes = bytes(target) if in_manifest else release.manifest_bytes
        signature = release.signature if in_manifest else bytes(target)
        with pytest.raises(ManifestError) as caught:
            verify_and_parse(manifest_bytes, signature)
        assert caught.value.code == "bad_signature"
    finally:
        key_module.PUBLIC_KEY = original


def test_an_oversize_manifest_is_refused_before_anything_else(monkeypatch: pytest.MonkeyPatch) -> None:
    use_key(monkeypatch, KEYS)
    big = b" " * (MAX_MANIFEST_BYTES + 1)
    assert code_of(lambda: verify_and_parse(big, KEYS.sign(big))) == "too_large"
    assert code_of(lambda: parse_manifest(big)) == "too_large"


# ---- content -------------------------------------------------------------------------------------------------------


def test_a_good_manifest_round_trips() -> None:
    release = build_release("1.2.3", KEYS)
    manifest = parse_manifest(release.manifest_bytes)
    assert set(manifest.assets) == {setup_asset_name("1.2.3"), zip_asset_name("1.2.3")}
    assert manifest.files["shelfsync/__init__.py"].size > 0
    assert release.manifest_bytes == canonical_bytes(json.loads(release.manifest_bytes))  # canonical form
    assert not release.manifest_bytes.endswith(b"\n")


def test_duplicate_keys_are_refused() -> None:
    text = release_text().replace('"format":1,', '"format":1,"format":1,')
    assert code_of(lambda: parse_manifest(text.encode())) == "bad_format"


def release_text() -> str:
    return build_release("0.0.2", KEYS).manifest_bytes.decode()


def test_duplicate_keys_inside_files_are_refused() -> None:
    text = release_text().replace(
        '"files":{',
        '"files":{"a.txt":{"size":1,"sha256":"' + "0" * 64 + '"},"a.txt":{"size":1,"sha256":"' + "0" * 64 + '"},',
    )
    assert code_of(lambda: parse_manifest(text.encode())) == "bad_format"


@pytest.mark.parametrize("constant", ["NaN", "Infinity", "-Infinity"])
def test_json_constants_that_are_not_json_are_refused(constant: str) -> None:
    text = release_text().replace('"schema_version":1', f'"schema_version":{constant}')
    assert code_of(lambda: parse_manifest(text.encode())) == "bad_format"


@pytest.mark.parametrize(
    "path",
    [
        "../evil",
        "a/../../evil",
        "/etc/passwd",
        "C:/Windows/x.dll",
        "c:evil",
        "a\\b",
        "a//b",
        "./a",
        "a/./b",
        "CON",
        "con.txt",
        "a/NUL.dll",
        "COM1",
        "lpt9.log",
        "COM\u00b9",
        "a/b.",
        "a/b ",
        "a:stream",
        "a/b*c",
        "a/b?c",
        'a/"b',
        "a/b\x00c",
        "a/\x07",
        "",
        "x" * 300,
    ],
)
def test_unsafe_paths_are_refused(path: str) -> None:
    assert not is_safe_relative_path(path)
    document = manifest_document()
    document["files"] = {path: {"size": 1, "sha256": "0" * 64}}
    assert code_of(lambda: parse_manifest(canonical_bytes(document))) == "bad_path"


@pytest.mark.parametrize(
    "path", ["a.txt", "ui/assets/index-abc123.js", "Lib/site-packages/x/__init__.py", "python314._pth", "a b/c.d"]
)
def test_ordinary_paths_are_fine(path: str) -> None:
    assert is_safe_relative_path(path)


def test_names_that_differ_only_in_case_are_refused() -> None:
    document = manifest_document()
    entry = {"size": 1, "sha256": "0" * 64}
    document["files"] = {"Lib/A.py": entry, "lib/a.PY": entry}
    assert code_of(lambda: parse_manifest(canonical_bytes(document))) == "bad_path"


@pytest.mark.parametrize(
    "mutate",
    [
        lambda d: d.update(extra=1),
        lambda d: d.pop("source_commit"),
        lambda d: d.update(format=2),
        lambda d: d.update(format=True),
        lambda d: d.update(app="other"),
        lambda d: d.update(version="0.0.02"),
        lambda d: d.update(version="0.0.2-rc1", tag="v0.0.2-rc1"),
        lambda d: d.update(source_commit="A" * 40),
        lambda d: d.update(source_commit="a" * 39),
        lambda d: d.update(built_at="2026-10-27 10:00:00"),
        lambda d: d.update(built_at="2026-13-45T10:00:00Z"),
        lambda d: d.update(schema_version=0),
        lambda d: d.update(schema_version="1"),
        lambda d: d.update(schema_version=True),
        lambda d: d.update(assets={}),
        lambda d: d.update(files={}),
        lambda d: d.update(files=[]),
        lambda d: d.update(assets={"a.exe": {"size": 1, "sha256": "0" * 64}}),
        lambda d: d["files"].update({"x.txt": {"size": 1}}),
        lambda d: d["files"].update({"x.txt": {"size": -1, "sha256": "0" * 64}}),
        lambda d: d["files"].update({"x.txt": {"size": 1, "sha256": "G" * 64}}),
        lambda d: d["files"].update({"x.txt": {"size": 1.0, "sha256": "0" * 64}}),
        lambda d: d["files"].update({"x.txt": {"size": 1, "sha256": "0" * 64, "mode": 1}}),
    ],
)
def test_unknown_missing_or_wrong_fields_are_refused(mutate: object) -> None:
    document = manifest_document()
    assert callable(mutate)
    mutate(document)
    code = code_of(lambda: parse_manifest(canonical_bytes(document)))
    assert code in ("bad_format", "tag_mismatch")


def test_not_an_object_or_not_utf8_is_refused() -> None:
    for data in (b"[]", b"3", b"null", b"\xff\xfe", b"", b'{"format":1}'):
        assert code_of(lambda data=data: parse_manifest(data)) == "bad_format"


def test_a_tag_that_is_not_v_plus_the_version_is_refused() -> None:
    document = manifest_document("0.0.2")
    document["tag"] = "v0.0.3"
    assert code_of(lambda: parse_manifest(canonical_bytes(document))) == "tag_mismatch"


# ---- what the updater accepts ---------------------------------------------------------------------------------------


def test_a_newer_version_from_its_own_release_is_acceptable() -> None:
    manifest = parse_manifest(build_release("0.0.2", KEYS).manifest_bytes)
    check_acceptable(manifest, installed="0.0.1", release_tag="v0.0.2")


def test_a_downgrade_and_the_same_version_are_refused() -> None:
    manifest = parse_manifest(build_release("0.0.2", KEYS).manifest_bytes)
    assert code_of(lambda: check_acceptable(manifest, installed="0.0.3", release_tag="v0.0.2")) == "not_newer"
    assert code_of(lambda: check_acceptable(manifest, installed="0.0.2", release_tag="v0.0.2")) == "not_newer"


def test_a_manifest_that_does_not_match_its_release_is_refused() -> None:
    manifest = parse_manifest(build_release("0.0.2", KEYS).manifest_bytes)
    assert code_of(lambda: check_acceptable(manifest, installed="0.0.1", release_tag="v0.0.9")) == "tag_mismatch"


def test_the_running_versions_own_manifest_must_be_that_version() -> None:
    manifest = parse_manifest(build_release("0.0.2", KEYS).manifest_bytes)
    check_is_version(manifest, version="0.0.2", release_tag="v0.0.2")
    assert code_of(lambda: check_is_version(manifest, version="0.0.1", release_tag="v0.0.2")) == "wrong_version"
    assert code_of(lambda: check_is_version(manifest, version="0.0.2", release_tag="v0.0.1")) == "tag_mismatch"


# ---- writing (CI) ---------------------------------------------------------------------------------------------------


def test_files_txt_is_read_as_path_size_sha256_per_line() -> None:
    digest = sha(b"abc")
    files = parse_files_txt(f"a.txt\t3\t{digest}\nui/b.js\t10\t{digest}\n\n")
    assert files == {"a.txt": FileEntry(3, digest), "ui/b.js": FileEntry(10, digest)}


@pytest.mark.parametrize(
    "text", ["a.txt 3 abc", "a.txt\t3", "a.txt\tx\t" + "0" * 64, "a\t1\t" + "0" * 64 + "\na\t2\t" + "0" * 64]
)
def test_a_bad_files_txt_is_refused(text: str) -> None:
    with pytest.raises(ManifestError):
        parse_files_txt(text)


def test_make_manifest_refuses_to_write_a_manifest_the_app_would_refuse() -> None:
    with pytest.raises(ManifestError):
        make_manifest(
            version="0.0.2",
            source_commit=COMMIT,
            built_at=BUILT_AT,
            schema_version=1,
            assets={setup_asset_name("0.0.2"): FileEntry(1, "0" * 64), zip_asset_name("0.0.2"): FileEntry(1, "0" * 64)},
            files=entries({"../x": b"1"}),
        )


def test_the_ci_command_writes_the_unsigned_manifest(tmp_path: Path) -> None:
    files_txt = tmp_path / "files.txt"
    files_txt.write_text(f"a.txt\t3\t{sha(b'abc')}\n", encoding="utf-8")
    setup, archive, out = tmp_path / "setup.exe", tmp_path / "x.zip", tmp_path / "manifest.json"
    setup.write_bytes(b"setup")
    archive.write_bytes(b"zip")
    code = main(
        [
            "--version",
            "0.0.2",
            "--source-commit",
            COMMIT,
            "--built-at",
            BUILT_AT,
            "--files-txt",
            str(files_txt),
            "--setup",
            str(setup),
            "--zip",
            str(archive),
            "--out",
            str(out),
        ]
    )
    assert code == 0
    manifest = parse_manifest(out.read_bytes())
    assert manifest.assets[zip_asset_name("0.0.2")] == FileEntry(3, sha(b"zip"))
    assert manifest.schema_version >= 1
    assert os.path.getsize(out) == len(out.read_bytes())
