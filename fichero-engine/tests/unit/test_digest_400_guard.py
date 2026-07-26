"""Tests for the digest 400 guard fix (#1198).

Before this fix, `_digest_library_database` used `Header(...)` (required),
which caused FastAPI to return 422 Unprocessable Entity when the
X-Fichero-Library-Path header was absent.  The fix changed the header to
`Header(default=None)` so the dependency always runs and the explicit
400 guard fires.

These tests use a raw TestClient without the conftest dependency override
so that `_digest_library_database` runs its real implementation.
"""

from __future__ import annotations




def _make_raw_client():
    """Return a TestClient with NO dependency overrides — exercises real guards."""
    from fastapi.testclient import TestClient
    from fichero.api.main import app

    # Must not inherit conftest's dependency_overrides — create a fresh client
    # with a clean override dict.
    client = TestClient(app, raise_server_exceptions=False)
    return client


class TestDigest400Guard:
    def test_no_header_returns_400_not_422(self):
        """GET /api/entities/digest with no X-Fichero-Library-Path must return 400."""
        client = _make_raw_client()
        r = client.get("/api/entities/digest")
        # Before fix: FastAPI returned 422 because the header dep was required.
        # After fix: the dep defaults to None and raises 400 explicitly.
        assert r.status_code == 400, (
            f"Expected 400 from missing header, got {r.status_code}: {r.text}"
        )

    def test_no_header_error_detail_mentions_library(self):
        """400 body should reference the missing library header."""
        client = _make_raw_client()
        r = client.get("/api/entities/digest")
        assert r.status_code == 400
        body = r.json()
        detail = body.get("detail", "")
        assert "X-Fichero-Library-Path" in detail or "library" in detail.lower()

    def test_empty_header_value_returns_400(self):
        """An empty X-Fichero-Library-Path value also triggers the 400 guard."""
        client = _make_raw_client()
        r = client.get(
            "/api/entities/digest",
            headers={"X-Fichero-Library-Path": ""},
        )
        assert r.status_code == 400

    def test_with_valid_header_does_not_return_422(self, tmp_path):
        """With a plausible (allowed) library path the response is not 422.

        We don't assert a specific success code because the path has no DB —
        we just confirm the old 422 regression no longer occurs.
        """
        lib_path = tmp_path / "TestLib.fichero"
        lib_path.mkdir()
        client = _make_raw_client()
        r = client.get(
            "/api/entities/digest",
            headers={"X-Fichero-Library-Path": str(lib_path)},
        )
        assert r.status_code != 422, (
            "422 must not be returned for a present (even invalid) header"
        )
