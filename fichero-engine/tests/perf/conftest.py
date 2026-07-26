"""Performance-test fixtures for the shared authenticated FastAPI app."""

import pytest

from fichero.api.auth import initialize_token


@pytest.fixture(autouse=True)
def _perf_test_auth_all_testclients(monkeypatch):
    """Preserve bootstrap auth when unit collection enabled shared middleware."""
    from starlette.testclient import TestClient

    token_header = f"Bearer {initialize_token()}"
    original_request = TestClient.request

    def _request_with_default_auth(self, *args, **kwargs):
        self.headers.setdefault("Authorization", token_header)
        return original_request(self, *args, **kwargs)

    monkeypatch.setattr(TestClient, "request", _request_with_default_auth)
    yield
