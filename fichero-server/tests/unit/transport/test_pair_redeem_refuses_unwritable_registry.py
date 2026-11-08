"""A registry that cannot be written refuses the redeem with a 503 and spends nothing (#6366): no swallowed failure."""

import pytest
from fastapi import HTTPException

from fichero_server.api.routes.auth import pairing


def test_unwritable_registry_refuses_instead_of_logging(monkeypatch):
    class Broken:
        def query(self, *_a, **_k):
            raise OSError("read-only")

    monkeypatch.setattr("fichero_server.api.routes.library.registry.get_global_database", lambda: Broken())
    with pytest.raises(HTTPException) as err:
        pairing._register_link_library("/tmp/Some Project")
    assert err.value.status_code == 503
