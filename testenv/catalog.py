"""The test stack's side of the catalog's client seam (m3.1 item 7; m3.0 Q1, Q2).

ShelfSync can't reach the test site itself: it doesn't trust the site's certificate, and the app gains no setting
([11] 2026-11-05). The catalog runner builds each store's client through a factory (`catalog.runner.ClientFactory`), so
the `-m teststack` tests (and m3.2's test-only launcher) give it this one: ShelfSync's own `WooClient` (GET only, no
redirects, no cookies), pointed at the test site through `laragon.make_transport` (127.0.0.1 only, the site's own
certificate and nothing else), with the site's **Read** key pair from the `ShelfSync-TestStack` Credential Manager
service. It serves the test site only: a store row with any other address is refused.

Developer tooling for the test stack: never shipped with the app.
"""

from pathlib import Path

from shelfsync.apply.woocommerce import WooClient
from shelfsync.catalog.runner import ClientFactory
from shelfsync.db.stores import StoreRow
from shelfsync.platform.secrets import SecretStore
from testenv.laragon import HarnessError, Site, TransportFactory, make_transport, pairs_for, read_pair, tls_context


def site_clients(
    site: Site, cert: Path, secrets: SecretStore, transport_factory: TransportFactory = make_transport
) -> ClientFactory:
    """A client factory for the test site: its Read pair (read once, here), its certificate, a new transport for
    every client. `HarnessError` when the Read pair isn't saved or the certificate can't be used."""
    pair = read_pair(secrets, pairs_for(site)[0])
    if pair is None:
        raise HarnessError(f"No read-only key pair is saved for {site.host}. Run the keys command first.")
    context = tls_context(cert)
    key, secret = pair

    def build(row: StoreRow) -> WooClient:
        if row.url != site.url:
            raise HarnessError("This client factory serves the test site only.")
        return WooClient(site.url, key, secret, transport=transport_factory(context, site.host))

    return build
