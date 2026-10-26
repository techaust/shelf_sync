"""SYS-03: the install token is read from the secret store once, before the port is bound."""

from shelfsync import server
from shelfsync.api.app import create_app
from shelfsync.paths import DataPaths
from shelfsync.platform.notify import FakeNotifier
from shelfsync.platform.secrets import MemorySecretStore, SecretStoreError
from shelfsync.secure.token import InstallToken
from tests.support import PORT
from tests.test_server import RecordingServe


class CountingStore(MemorySecretStore):
    """Counts reads; every read after the first one fails, as a store that goes away after start-up would."""

    def __init__(self) -> None:
        super().__init__()
        self.gets = 0

    def get(self, name: str) -> str | None:
        self.gets += 1
        if self.gets > 1:
            raise SecretStoreError("the store went away")
        return super().get(name)


def test_start_up_reads_the_store_once_and_the_app_never_reads_it_again(data_paths: DataPaths) -> None:
    """SYS-03: a second read after the bind would be a second place for start-up to fail with a port held. With
    the token built once before the bind and handed over, the store's second `get` never happens."""
    store = CountingStore()
    serve = RecordingServe()
    code = server.run(data_paths, FakeNotifier(), serve, 0.0, store)
    assert code == server.EXIT_OK
    assert serve.app is not None  # the server was started
    assert store.gets == 1


def test_create_app_with_a_ready_token_does_not_touch_the_store() -> None:
    """SYS-03: the token holder passed in is used as it is."""
    store = CountingStore()
    holder = InstallToken(store)
    assert store.gets == 1
    create_app(PORT, store, install_token=holder)
    assert store.gets == 1


def test_a_store_that_fails_on_the_first_read_never_starts_the_server(data_paths: DataPaths) -> None:
    """SYS-03: the failure comes before the bind."""

    class FailsAtOnce(CountingStore):
        def get(self, name: str) -> str | None:
            self.gets += 1
            raise SecretStoreError("no store")

    store = FailsAtOnce()
    serve = RecordingServe()
    code = server.run(data_paths, FakeNotifier(), serve, 0.0, store)
    assert code == server.EXIT_START_FAILED
    assert serve.app is None and serve.sockname is None
    assert store.gets == 1
