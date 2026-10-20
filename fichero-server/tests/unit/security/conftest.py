"""The keychain keeps a found or absent answer for five minutes (`keychain._LOOKUPS`, with its STATE: found, absent or
unreadable). A test that fakes `security`'s output must not meet the answer an earlier test left: forget them around each."""
import pytest


@pytest.fixture(autouse=True)
def _forget_cached_keychain_lookups():
    from fichero_server.security import keychain

    keychain.forget_cached_lookups()
    yield
    keychain.forget_cached_lookups()
