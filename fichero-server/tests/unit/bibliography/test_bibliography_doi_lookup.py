"""Offline hardening for the DOI / ISBN resolvers (#910).

ZERO real network: ``httpx.AsyncClient`` is monkeypatched at the module boundary
(the resolvers do a local ``import httpx``, so patching the attribute on the real
httpx module is enough). The per-process ``_cache`` is cleared before each test.
Async functions are driven with ``asyncio.run`` — no pytest-asyncio dependency.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

import fichero_server.bibliography.doi_lookup as dl
from fichero_server.bibliography.doi_lookup import (
    _normalize_doi,
    _normalize_isbn,
    resolve_doi,
    resolve_isbn,
    resolve_many,
)


@pytest.fixture(autouse=True)
def _clear_cache():
    dl._cache.clear()
    yield
    dl._cache.clear()


# --- fake httpx client -----------------------------------------------------


class _FakeResp:
    def __init__(self, status_code: int, payload):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        return self._payload


def _patch_httpx(monkeypatch, *, status=200, payload=None, raise_exc=None):
    resp = _FakeResp(status, {} if payload is None else payload)

    class _FakeClient:
        def __init__(self, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def get(self, _url):
            if raise_exc is not None:
                raise raise_exc
            return resp

    monkeypatch.setattr(httpx, "AsyncClient", _FakeClient)


# ===========================================================================
# 1. _normalize_doi / _normalize_isbn (pure)
# ===========================================================================


def test_normalize_doi_strips_url_and_doi_prefixes():
    assert _normalize_doi("https://doi.org/10.1/ABC") == "10.1/ABC"
    assert _normalize_doi("http://doi.org/10.2/x") == "10.2/x"
    assert _normalize_doi("doi:10.3/y") == "10.3/y"
    # Prefix match is case-insensitive; DOI body case is preserved (DOIs are
    # case-sensitive after the prefix).
    assert _normalize_doi("HTTPS://DOI.ORG/10.4/MixedCase") == "10.4/MixedCase"


def test_normalize_doi_trims_and_strips_trailing_slash():
    assert _normalize_doi("  10.5/z/  ") == "10.5/z"
    assert _normalize_doi("10.6/plain") == "10.6/plain"


def test_normalize_doi_empty():
    assert _normalize_doi("") == ""
    assert _normalize_doi("   ") == ""


def test_normalize_isbn_strips_hyphens_and_spaces():
    assert _normalize_isbn("978-3-16-148410-0") == "9783161484100"
    assert _normalize_isbn("  0 306 40615 2 ") == "0306406152"
    # X check digit preserved and upper-cased.
    assert _normalize_isbn("080442957x") == "080442957X"


def test_normalize_isbn_already_clean_and_garbage():
    assert _normalize_isbn("9783161484100") == "9783161484100"
    assert _normalize_isbn("") == ""
    assert _normalize_isbn("not-an-isbn") == ""  # no digits/X -> empty, no crash


# ===========================================================================
# 2. resolve_doi — Crossref response parsing
# ===========================================================================

CROSSREF_FULL = {
    "message": {
        "title": ["The Title"],
        "author": [
            {"family": "Doe", "given": "Jane"},
            {"family": "Solo"},  # family only
        ],
        "issued": {"date-parts": [[2019, 5, 1]]},
        "publisher": "ACME",
        "container-title": ["J. Testing"],
        "volume": 12,
        "issue": 3,
        "page": "45-67",
        "ISBN": ["978-3-16-148410-0"],
        "ISSN": ["1234-5678"],
        "language": "en",
    }
}


def test_resolve_doi_maps_full_crossref_message(monkeypatch):
    _patch_httpx(monkeypatch, payload=CROSSREF_FULL)
    out = asyncio.run(resolve_doi("10.1/ABC"))
    assert out["doi"] == "10.1/ABC"
    assert out["title"] == "The Title"
    assert out["authors"] == ["Doe, Jane", "Solo"]
    assert out["date"] == "2019"
    assert out["publisher"] == "ACME"
    assert out["journal"] == "J. Testing"
    assert out["volume"] == "12"
    assert out["issue"] == "3"
    assert out["pages"] == "45-67"
    assert out["isbn_13"] == "9783161484100"
    assert out["issn"] == "1234-5678"
    assert out["language"] == "en"
    assert out["metadata"]["crossref"] is True


def test_resolve_doi_missing_fields_degrade_gracefully(monkeypatch):
    _patch_httpx(monkeypatch, payload={"message": {"title": ["Only Title"]}})
    out = asyncio.run(resolve_doi("10.9/min"))
    assert out["title"] == "Only Title"
    assert out["doi"] == "10.9/min"
    # No KeyError, and absent fields simply not present.
    assert "authors" not in out
    assert "date" not in out
    assert out["metadata"]["crossref"] is True


def test_resolve_doi_empty_message_is_minimal_not_crash(monkeypatch):
    # A 200 with an empty message yields a minimal dict (doi + provenance),
    # never a fabricated title and never a crash.
    _patch_httpx(monkeypatch, payload={"message": {}})
    out = asyncio.run(resolve_doi("10.0/empty"))
    assert out["doi"] == "10.0/empty"
    assert "title" not in out


def test_resolve_doi_non_200_returns_empty(monkeypatch):
    _patch_httpx(monkeypatch, status=404, payload={"message": {"title": ["Nope"]}})
    assert asyncio.run(resolve_doi("10.1/missing")) == {}


def test_resolve_doi_network_failure_returns_empty(monkeypatch):
    _patch_httpx(monkeypatch, raise_exc=RuntimeError("boom"))
    assert asyncio.run(resolve_doi("10.1/boom")) == {}


def test_resolve_doi_empty_input_short_circuits(monkeypatch):
    # Never even constructs a client.
    def _explode(**kwargs):
        raise AssertionError("should not hit network for empty DOI")

    monkeypatch.setattr(httpx, "AsyncClient", _explode)
    assert asyncio.run(resolve_doi("   ")) == {}


# ===========================================================================
# 3. resolve_isbn — Open Library response parsing
# ===========================================================================

OPENLIB_FULL = {
    "ISBN:9783161484100": {
        "title": "Book Title",
        "authors": [{"name": "Jane Doe"}, {"name": "John Roe"}],
        "publish_date": "2005",
        "publishers": [{"name": "Penguin"}],
    }
}


def test_resolve_isbn_maps_openlibrary_entry(monkeypatch):
    _patch_httpx(monkeypatch, payload=OPENLIB_FULL)
    out = asyncio.run(resolve_isbn("978-3-16-148410-0"))
    assert out["isbn_13"] == "9783161484100"
    assert out["title"] == "Book Title"
    assert out["authors"] == ["Jane Doe", "John Roe"]
    assert out["date"] == "2005"
    assert out["publisher"] == "Penguin"
    assert out["metadata"]["open_library"] is True


def test_resolve_isbn_missing_entry_returns_empty(monkeypatch):
    # Response has no matching ISBN: key.
    _patch_httpx(monkeypatch, payload={})
    assert asyncio.run(resolve_isbn("9783161484100")) == {}


def test_resolve_isbn_non_200_returns_empty(monkeypatch):
    _patch_httpx(monkeypatch, status=500, payload=OPENLIB_FULL)
    assert asyncio.run(resolve_isbn("9783161484100")) == {}


def test_resolve_isbn_empty_input_short_circuits(monkeypatch):
    def _explode(**kwargs):
        raise AssertionError("should not hit network for empty ISBN")

    monkeypatch.setattr(httpx, "AsyncClient", _explode)
    assert asyncio.run(resolve_isbn("---")) == {}


# ===========================================================================
# 4. resolve_many — batch aggregation shape
# ===========================================================================


def test_resolve_many_aggregates_by_key(monkeypatch):
    async def fake_doi(d, timeout=10.0):
        return {"src": "doi", "key": d}

    async def fake_isbn(i, timeout=10.0):
        return {"src": "isbn", "key": i}

    monkeypatch.setattr(dl, "resolve_doi", fake_doi)
    monkeypatch.setattr(dl, "resolve_isbn", fake_isbn)

    out = asyncio.run(resolve_many(dois=["10.1/a", "10.2/b"], isbns=["9783161484100"]))
    assert set(out.keys()) == {"10.1/a", "10.2/b", "9783161484100"}
    assert out["10.1/a"]["src"] == "doi"
    assert out["9783161484100"]["src"] == "isbn"


def test_resolve_many_empty_returns_empty_dict():
    assert asyncio.run(resolve_many()) == {}
