"""`python -m testenv.laragon seed` (m2.8): the sample products and their files, against an in-memory fake
WooCommerce served over HTTPS on 127.0.0.1 with the harness's own certificate (WooCommerce REST v3 behaviour as its
docs describe it: products, variations, trash and force delete), and the real moto server for the files."""

import hashlib
import io
import json
import logging
import re
import socket
import uuid
import zipfile
from collections.abc import Iterator
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs

import pytest

from shelfsync.platform.secrets import MemorySecretStore
from testenv import laragon, moto_s3, samples, seed
from tests.laragon_support import (
    ALL_VALUES,
    RO_KEY,
    RO_SECRET,
    RW_KEY,
    RW_SECRET,
    SITE,
    basic,
    json_answer,
    site,
    store_with_keys,
    write_site_cert,
)
from tests.tls_support import RecordedRequest, RunningServer, tls_server

PRODUCT = re.compile(r"/wp-json/wc/v3/products/(\d+)")
VARIATIONS = re.compile(r"/wp-json/wc/v3/products/(\d+)/variations")
VARIATION = re.compile(r"/wp-json/wc/v3/products/(\d+)/variations/(\d+)")
Answer = tuple[int, dict[str, str], bytes]


@dataclass
class FakeStore:
    """WooCommerce's products and variations in memory, as the REST v3 docs describe them: `status=any` leaves the
    trash out and `include_status=trash` lists it; DELETE without `force` trashes (WordPress then gives the slug a
    `__trashed` suffix), with `force=true` removes the product and its variations; a slug already taken gets `-2`;
    download and meta IDs are kept when sent back and made up otherwise. HTTP Basic with the read/write pair."""

    products: dict[int, dict[str, Any]] = field(default_factory=dict)
    variations: dict[int, dict[int, dict[str, Any]]] = field(default_factory=dict)
    next_id: int = 100
    page_size: int = 5  # small, so listing pages
    authorization: str = field(default_factory=lambda: basic(RW_KEY, RW_SECRET))
    redirect_writes: bool = False
    refuse_creates: bool = False
    tamper_on_read: int | None = None

    def new_id(self) -> int:
        self.next_id += 1
        return self.next_id

    def _downloads(self, given: Any) -> list[dict[str, Any]]:
        return [{**entry, "id": entry.get("id") or uuid.uuid4().hex} for entry in given or []]

    def _meta(self, given: Any) -> list[dict[str, Any]]:
        return [{"id": self.new_id(), **entry} for entry in given or []]

    def _slug(self, wanted: str, own_id: int | None = None) -> str:
        taken = {p["slug"] for i, p in self.products.items() if i != own_id}
        slug, n = wanted, 2
        while slug in taken:
            slug, n = f"{wanted}-{n}", n + 1
        return slug

    def add(self, **fields: Any) -> dict[str, Any]:
        """A product put in by hand (not through seed)."""
        product_id = self.new_id()
        product = {"id": product_id, "sku": "", "type": "simple", "status": "publish", "meta_data": [], **fields}
        product["meta_data"] = self._meta(product["meta_data"])
        self.products[product_id] = product
        return product

    def _apply(self, target: dict[str, Any], body: dict[str, Any], own_id: int | None) -> None:
        for name, value in body.items():
            if name == "downloads":
                target["downloads"] = self._downloads(value)
            elif name == "meta_data":
                target["meta_data"] = self._meta(value)
            elif name == "slug":
                target["slug"] = self._slug(value, own_id)
            else:
                target[name] = value

    def __call__(self, request: RecordedRequest) -> Answer:
        if request.headers.get("Authorization") != self.authorization:
            return json_answer(401, {"code": "woocommerce_rest_cannot_view", "message": "Sorry."})
        if self.redirect_writes and request.method != "GET":
            return 302, {"Location": "https://store-a.example/wp-json/wc/v3/products"}, b""
        body = json.loads(request.body) if request.body else {}
        query = {name: values[0] for name, values in parse_qs(request.target.partition("?")[2]).items()}
        path = request.path
        if match := VARIATION.fullmatch(path):
            parent, variation_id = int(match[1]), int(match[2])
            variation = self.variations[parent][variation_id]
            self._apply(variation, body, None)
            return json_answer(200, variation)
        if match := VARIATIONS.fullmatch(path):
            parent = int(match[1])
            if request.method == "GET":
                return json_answer(200, list(self.variations.get(parent, {}).values()))
            variation = {"id": self.new_id(), "sku": ""}
            self._apply(variation, body, None)
            self.variations.setdefault(parent, {})[variation["id"]] = variation
            return json_answer(201, variation)
        if match := PRODUCT.fullmatch(path):
            product_id = int(match[1])
            if product_id not in self.products:
                return json_answer(404, {"code": "woocommerce_rest_product_invalid_id", "message": "Invalid ID."})
            product = self.products[product_id]
            if request.method == "GET":
                if self.tamper_on_read == product_id:
                    product["slug"] = "tampered"
                return json_answer(200, product)
            if request.method == "PUT":
                self._apply(product, body, product_id)
                return json_answer(200, product)
            if query.get("force") == "true":
                del self.products[product_id]
                self.variations.pop(product_id, None)
            else:
                product["status"] = "trash"
                product["slug"] = f"{product['slug']}__trashed"
            return json_answer(200, product)
        if path == "/wp-json/wc/v3/products":
            if request.method == "POST":
                if self.refuse_creates:
                    return json_answer(400, {"code": "woocommerce_rest_product_invalid", "message": "No."})
                product = {"id": self.new_id(), "sku": "", "slug": ""}
                self._apply(product, body, product["id"])
                self.products[product["id"]] = product
                return json_answer(201, product)
            if "include_status" in query:
                wanted = set(query["include_status"].split(","))
                chosen = [p for p in self.products.values() if p["status"] in wanted]
            else:
                chosen = [p for p in self.products.values() if p["status"] != "trash"]
            size = min(int(query.get("per_page", "10")), self.page_size)
            page = int(query.get("page", "1"))
            pages = max(1, -(-len(chosen) // size))
            headers = {"X-WP-Total": str(len(chosen)), "X-WP-TotalPages": str(pages)}
            return json_answer(200, chosen[(page - 1) * size : page * size], headers)
        return json_answer(404, {"code": "rest_no_route", "message": "No route."})

    def marked(self) -> dict[str, dict[str, Any]]:
        return {seed.marker_of(p) or "": p for p in self.products.values() if seed.marker_of(p)}


@pytest.fixture(autouse=True)
def no_spacing(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(seed, "SPACING_S", 0.0)


@pytest.fixture(scope="module")
def site_cert() -> laragon.SiteCertificate:
    return laragon.make_site_certificate(SITE)


@pytest.fixture
def fake(site_cert: laragon.SiteCertificate, tmp_path: Path) -> Iterator[tuple[RunningServer, FakeStore]]:
    store = FakeStore()
    with tls_server((site_cert.cert_pem, site_cert.key_pem), tmp_path / "server", store) as server:
        yield server, store


@pytest.fixture
def cert_file(site_cert: laragon.SiteCertificate, tmp_path: Path) -> Path:
    return write_site_cert(tmp_path / "trust", site_cert)


def unused_port() -> int:
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return int(probe.getsockname()[1])


def run(port: int, cert: Path, *extra: str, keys: MemorySecretStore | None = None, moto: str | None = None) -> int:
    store = keys if keys is not None else store_with_keys()
    argv = ["seed", "--site", f"https://{SITE}:{port}", "--cert", str(cert)]
    argv += ["--moto", moto or f"http://127.0.0.1:{unused_port()}", *extra]
    return laragon.main(argv, secrets_factory=lambda: store)


def writes(server: RunningServer) -> list[tuple[str, str]]:
    return [(r.method, r.path) for r in server.record.requests if r.method != "GET"]


# ---------- the sample list itself ----------


def test_the_samples_are_shaped_like_the_real_catalogue() -> None:
    chosen = samples.SAMPLES
    assert len(chosen) == 13
    assert len({s.id for s in chosen}) == len({s.slug for s in chosen}) == 13
    assert {s.status for s in chosen} == set(samples.STATUSES)
    assert sum(1 for s in chosen if s.type == "variable") == 1
    assert [s.id for s in chosen if not s.all_files()] == ["setup-service"]
    assert [s.id for s in chosen if len(s.files) == 2] == ["northwind"]
    keys = [f.key for s in chosen for f in s.all_files()]
    assert len(keys) == 14 and len(set(keys)) == 13  # two samples share one key
    for key in keys:
        assert re.fullmatch(r"(productrepo/)?[a-z0-9-]+(-\d+(\.\d+)+)?\.zip", key), key
    assert "lantern.zip" in keys and "productrepo/emberline.zip" in keys  # a root-level and an unversioned key
    # each slug is its key's stem (CAT-02/CAT-04), except where it can't be: no file, variations, or a shared key
    for sample in chosen:
        if sample.files and sample.id != "mosaic-gallery-bundle":
            assert sample.slug == sample.files[0].stem, sample.id
    variation_ids = [v.id for s in chosen for v in s.variations]
    assert len(set(variation_ids)) == 2 and not set(variation_ids) & {s.id for s in chosen}


def test_no_sample_payload_carries_a_sku() -> None:
    for sample in samples.SAMPLES:
        assert "sku" not in seed.new_product(sample)
        for variation in sample.variations:
            assert "sku" not in seed.new_variation(variation)


def test_each_file_is_a_tiny_fixed_zip_with_only_a_header() -> None:
    for file in samples.unique_files(samples.SAMPLES):
        body = file.zip_bytes()
        assert body == file.zip_bytes()  # the same bytes every time
        assert len(body) < 1024
        with zipfile.ZipFile(io.BytesIO(body)) as archive:
            (entry,) = archive.infolist()
            text = archive.read(entry).decode("utf-8")
        assert entry.date_time == (1980, 1, 1, 0, 0, 0)
        if file.kind == "theme":
            assert entry.filename == f"{file.stem}/style.css"
            assert f"Theme Name: {file.title}\nVersion: {file.version}\n" in text
        else:
            assert entry.filename == f"{file.stem}/{file.stem}.php"
            assert f" * Plugin Name: {file.title}\n * Version: {file.version}\n" in text
        assert "No vendor code" in text


# ---------- seed ----------


def test_seed_writes_every_sample(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    assert run(server.port, cert_file) == 0
    marked = store.marked()
    assert set(marked) == {s.id for s in samples.SAMPLES}
    for sample in samples.SAMPLES:
        product = marked[sample.id]
        assert product["sku"] == ""
        assert product["slug"] in sample.accepted_slugs()
        assert product["status"] == sample.status
        assert product["type"] == sample.type
        assert [(d["name"], d["file"]) for d in product.get("downloads", [])] == [
            (f.name, f'[amazon_s3 object="{f.key}"]') for f in sample.files
        ]
    assert marked["old-slider"]["slug"] == "old-slider__trashed"
    lumen = store.variations[marked["lumen-suite"]["id"]]
    assert sorted(seed.marker_of(v) or "" for v in lumen.values()) == [
        "lumen-suite/single-site",
        "lumen-suite/unlimited",
    ]
    assert all(v["sku"] == "" and v["downloadable"] is True for v in lumen.values())
    out = capsys.readouterr().out
    assert "The S3 server isn't running at" in out
    assert f"13 samples on {SITE}: 13 created, 0 updated, 0 unchanged, 0 recreated." in out
    assert "Created old-slider (#" in out and "(in the trash)." in out


def test_seeding_twice_writes_nothing_the_second_time(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    assert run(server.port, cert_file) == 0
    before = json.dumps([store.products, store.variations], sort_keys=True, default=str)
    count = len(server.record.requests)
    assert run(server.port, cert_file) == 0
    assert [r for r in server.record.requests[count:] if r.method != "GET"] == []
    assert json.dumps([store.products, store.variations], sort_keys=True, default=str) == before  # same IDs too
    assert (
        "13 samples on shelfsync-test.test: 0 created, 0 updated, 13 unchanged, 0 recreated." in capsys.readouterr().out
    )


def test_a_drifted_sample_gets_only_its_differences_and_keeps_its_download_ids(
    fake: tuple[RunningServer, FakeStore], cert_file: Path
) -> None:
    server, store = fake
    assert run(server.port, cert_file) == 0
    northwind = store.marked()["northwind"]
    kept_id = northwind["downloads"][0]["id"]
    northwind["downloads"][1]["file"] = '[amazon_s3 object="productrepo/something-else.zip"]'
    northwind["regular_price"] = "5"
    variation = next(iter(store.variations[store.marked()["lumen-suite"]["id"]].values()))
    variation["downloadable"] = False
    count = len(server.record.requests)
    assert run(server.port, cert_file) == 0
    sent = [(r.method, r.path, json.loads(r.body)) for r in server.record.requests[count:] if r.method != "GET"]
    assert [(method, sorted(body)) for method, _, body in sent] == [
        ("PUT", ["downloads", "regular_price"]),
        ("PUT", ["downloadable"]),
    ]
    assert sent[0][2]["downloads"][0] == {
        "id": kept_id,
        "name": "northwind-5.0.2.zip",
        "file": northwind["downloads"][0]["file"],
    }
    assert "id" not in sent[0][2]["downloads"][1]
    assert store.marked()["northwind"]["downloads"][0]["id"] == kept_id


def test_the_wrong_type_or_trash_state_is_made_again(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    assert run(server.port, cert_file) == 0
    old = {name: store.marked()[name]["id"] for name in ("lumen-suite", "old-slider", "aurora")}
    store.marked()["lumen-suite"]["type"] = "simple"
    store.marked()["old-slider"]["status"] = "publish"  # taken out of the trash by hand
    store.marked()["old-slider"]["slug"] = "old-slider"
    store.marked()["aurora"]["status"] = "trash"  # trashed by hand
    assert run(server.port, cert_file) == 0
    marked = store.marked()
    assert all(marked[name]["id"] != old[name] for name in old)
    assert old["lumen-suite"] not in store.variations
    assert marked["old-slider"]["status"] == "trash" and marked["aurora"]["status"] == "publish"
    assert len(store.variations[marked["lumen-suite"]["id"]]) == 2
    assert "0 created, 0 updated, 10 unchanged, 3 recreated." in capsys.readouterr().out


def test_a_product_holding_a_samples_slug_stops_seed_before_any_write(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    mine = store.add(name="My own Aurora", slug="aurora")
    assert run(server.port, cert_file) == 1
    assert writes(server) == []
    assert f"Product #{mine['id']} isn't the sample aurora but uses its slug 'aurora'" in capsys.readouterr().err


def test_two_products_with_one_marker_stop_seed(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    marker = [{"key": samples.MARKER_KEY, "value": "aurora"}]
    first, second = store.add(slug="aurora", meta_data=marker), store.add(slug="aurora-2", meta_data=marker)
    assert run(server.port, cert_file) == 1
    assert writes(server) == []
    assert f"Products #{first['id']}, #{second['id']} are all marked as sample aurora" in capsys.readouterr().err


def test_seed_never_follows_a_redirect(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    store.redirect_writes = True
    assert run(server.port, cert_file) == 1
    assert len(writes(server)) == 1  # the first write, answered 302, and nothing after it
    err = capsys.readouterr().err
    assert "to another address (store-a.example) (HTTP 302); seed never follows that" in err


def test_a_refused_write_names_the_code_and_status(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    store.refuse_creates = True
    assert run(server.port, cert_file) == 1
    assert (
        "WooCommerce refused POST /wp-json/wc/v3/products (woocommerce_rest_product_invalid, HTTP 400)."
        in capsys.readouterr().err
    )


def test_the_keys_go_in_the_header_only(
    fake: tuple[RunningServer, FakeStore],
    cert_file: Path,
    capsys: pytest.CaptureFixture[str],
    caplog: pytest.LogCaptureFixture,
) -> None:
    server, _ = fake
    caplog.set_level(logging.DEBUG)
    assert run(server.port, cert_file) == 0
    assert run(server.port, cert_file, "--reset") == 0
    for request in server.record.requests:
        assert request.headers["Authorization"] == basic(RW_KEY, RW_SECRET)
        assert not any(value in request.target or value.encode() in request.body for value in ALL_VALUES)
    captured = capsys.readouterr()
    assert not any(value in captured.out + captured.err + caplog.text for value in ALL_VALUES)
    assert {r.headers["Host"] for r in server.record.requests} == {f"{SITE}:{server.port}"}


def test_seed_with_another_certificate_writes_nothing(
    fake: tuple[RunningServer, FakeStore], tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, _ = fake
    other = write_site_cert(tmp_path / "other", laragon.make_site_certificate(SITE))
    assert run(server.port, other) == 1
    assert server.record.requests == []
    assert "The site's security certificate wasn't accepted. Nothing was written." in capsys.readouterr().err


def test_seed_needs_the_read_write_pair(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, _ = fake
    only_ro = MemorySecretStore()
    ro, _ = laragon.pairs_for(site())
    only_ro.set(ro.key_entry, RO_KEY)
    only_ro.set(ro.secret_entry, RO_SECRET)
    assert run(server.port, cert_file, keys=only_ro) == 1
    assert "No read/write key pair is saved for shelfsync-test.test" in capsys.readouterr().err
    assert server.record.sni_names == []


def test_seed_spaces_its_requests_as_settings_does(fake: tuple[RunningServer, FakeStore], cert_file: Path) -> None:
    server, _ = fake
    pauses: list[float] = []
    seed.run_seed(
        site(server.port),
        cert_file,
        store_with_keys(),
        f"http://127.0.0.1:{unused_port()}",
        "b",
        "us-east-1",
        laragon.make_transport,
        sleep=pauses.append,
        samples=samples.SAMPLES[:2],
    )
    assert len(pauses) == len(server.record.requests) - 1
    assert set(pauses) == {seed.SPACING_S}


def test_a_key_name_never_goes_in_a_query_string() -> None:
    client = seed.SeedClient(site(), RW_KEY, RW_SECRET, laragon.LoopbackOnlyTransport(moto_s3_unused(), SITE))
    with client, pytest.raises(ValueError, match="never go in a query string"):
        client.call("GET", seed.PRODUCTS, {"consumer_key": "x"})


def moto_s3_unused() -> Any:
    import httpx

    return httpx.MockTransport(lambda request: httpx.Response(500))


# ---------- --reset ----------


def test_reset_deletes_the_samples_and_nothing_else(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    assert run(server.port, cert_file) == 0
    lumen_id = store.marked()["lumen-suite"]["id"]
    mine = store.add(name="My product", slug="my-product")
    no_slug = store.add(name="No slug", slug="")
    wrong_slug = store.add(slug="not-aurora", meta_data=[{"key": samples.MARKER_KEY, "value": "aurora-copy"}])
    renamed = store.add(slug="renamed", meta_data=[{"key": samples.MARKER_KEY, "value": "aurora"}])
    capsys.readouterr()
    assert run(server.port, cert_file, "--reset") == 0
    assert set(store.products) == {mine["id"], no_slug["id"], wrong_slug["id"], renamed["id"]}
    assert lumen_id not in store.variations
    out = capsys.readouterr().out
    assert "Deleted old-slider (#" in out  # its trashed slug, old-slider__trashed, is accepted
    assert f"Deleted 13 sample products from {SITE}." in out
    assert f"Kept #{wrong_slug['id']}: marked 'aurora-copy', but it isn't one of the samples as listed." in out
    assert f"Kept #{renamed['id']}: marked 'aurora', but it isn't one of the samples as listed." in out
    deletes = [r for r in server.record.requests if r.method == "DELETE" and "force=true" in r.target]
    assert len(deletes) == 13


def test_reset_rereads_each_product_before_deleting_it(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    assert run(server.port, cert_file) == 0
    aurora = store.marked()["aurora"]["id"]
    store.tamper_on_read = aurora  # its slug changes between the listing and the delete
    assert run(server.port, cert_file, "--reset") == 0  # the changed one is no longer a sample: nothing left
    assert aurora in store.products
    out = capsys.readouterr().out
    assert f"Kept #{aurora}: it changed while reset ran." in out
    assert f"Deleted 12 sample products from {SITE}." in out


def test_reset_on_a_site_without_samples_deletes_nothing(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, store = fake
    store.add(name="Mine", slug="aurora")
    assert run(server.port, cert_file, "--reset") == 0
    assert writes(server) == []
    assert f"Deleted 0 sample products from {SITE}." in capsys.readouterr().out


# ---------- the files on moto ----------


@pytest.mark.parametrize(
    "value",
    [
        "https://127.0.0.1:47630",
        "http://s3.amazonaws.com",
        "http://10.0.0.1:47630",
        "http://127.0.0.1",
        "http://127.0.0.1:0",
        "http://user:pw@127.0.0.1:47630",
        "http://127.0.0.1:47630/bucket",
    ],
)
def test_seed_refuses_any_s3_but_the_local_server(value: str, capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as raised:
        laragon.main(["seed", "--moto", value], secrets_factory=MemorySecretStore)
    assert raised.value.code == 2
    assert "use the local S3 server" in capsys.readouterr().err


def test_seed_uploads_every_file_to_moto_on_every_run(
    fake: tuple[RunningServer, FakeStore], cert_file: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    server, _ = fake
    running = moto_s3.start(port=0)
    try:
        assert run(server.port, cert_file, moto=running.endpoint) == 0
        client = moto_s3.s3_client(running.endpoint, running.region)
        try:
            listed = client.list_objects_v2(Bucket=running.bucket)["Contents"]
            files = {f.key: f for f in samples.unique_files(samples.SAMPLES)}
            assert sorted(entry["Key"] for entry in listed) == sorted(files)
            for entry in listed:
                body = files[entry["Key"]].zip_bytes()
                assert entry["ETag"].strip('"') == hashlib.md5(body).hexdigest()
                answer = client.get_object(Bucket=running.bucket, Key=entry["Key"])
                with answer["Body"] as stream:
                    assert stream.read() == body
            client.delete_object(Bucket=running.bucket, Key="lantern.zip")  # as if moto lost it
            assert run(server.port, cert_file, moto=running.endpoint) == 0
            assert client.head_object(Bucket=running.bucket, Key="lantern.zip")["ContentLength"] > 0
        finally:
            client.close()
    finally:
        running.stop()
    out = capsys.readouterr().out
    assert out.count(f"Uploaded 13 sample files to {running.bucket} at {running.endpoint}.") == 2
