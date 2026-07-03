from __future__ import annotations

from types import SimpleNamespace

from fichero.api.main import assert_library_read_authorized, assert_library_write_authorized


def _bootstrap_request():
    return SimpleNamespace(state=SimpleNamespace(bootstrap_auth=True, user=None))


def test_bootstrap_auth_bypasses_library_read_authorization():
    result = assert_library_read_authorized(_bootstrap_request(), "/tmp/example.fichero")
    assert result is None


def test_bootstrap_auth_bypasses_library_write_authorization():
    result = assert_library_write_authorized(_bootstrap_request(), "/tmp/example.fichero")
    assert result is None
