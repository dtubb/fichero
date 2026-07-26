"""Coverage for the two remaining pure-logic bibliography route paths:
``resolve`` (DOI/ISBN merge precedence) and ``export_bibtex`` (multi-doc export).

No network: ``resolve_doi`` / ``resolve_isbn`` are monkeypatched on
``fichero.bibliography.doi_lookup`` (the route imports them locally, so patching
the module attribute is enough). Driven through the authenticated TestClient so
the full route -> registry.invoke -> patch_metadata chain runs.
"""

from __future__ import annotations


import fichero.bibliography.doi_lookup as doi_lookup
from fichero.bibliography.importers import read_bibtex
from fichero.models import Document


def _stub_resolvers(monkeypatch, *, doi_result=None, isbn_result=None):
    async def fake_doi(_doi):
        return dict(doi_result or {})

    async def fake_isbn(_isbn):
        return dict(isbn_result or {})

    monkeypatch.setattr(doi_lookup, "resolve_doi", fake_doi)
    monkeypatch.setattr(doi_lookup, "resolve_isbn", fake_isbn)


# ---------------------------------------------------------------------------
# resolve() — merge precedence: existing curated metadata WINS
# ---------------------------------------------------------------------------


def test_resolve_doi_existing_curated_values_win(client, db, monkeypatch):
    doc = Document(name="paper.pdf", source_metadata={"title": "Curated", "author": "Me"})
    db.save(doc)
    _stub_resolvers(
        monkeypatch,
        doi_result={"title": "Resolved", "doi": "10.1/x", "publisher": "ACME"},
    )

    resp = client.post(
        f"/api/bibliography/resolve?document_id={doc.id}",
        json={"doi": "10.1/x"},
    )
    assert resp.status_code == 200, resp.text
    meta = resp.json()["metadata"]
    # Existing non-empty key survives; resolved value does NOT overwrite it.
    assert meta["title"] == "Curated"
    assert meta["author"] == "Me"
    # New keys are added.
    assert meta["doi"] == "10.1/x"
    assert meta["publisher"] == "ACME"


def test_resolve_skips_empty_resolved_values(client, db, monkeypatch):
    doc = Document(name="paper.pdf", source_metadata={"title": "Curated"})
    db.save(doc)
    _stub_resolvers(
        monkeypatch,
        doi_result={"publisher": "", "doi": "10.2/y", "language": None},
    )

    resp = client.post(
        f"/api/bibliography/resolve?document_id={doc.id}",
        json={"doi": "10.2/y"},
    )
    assert resp.status_code == 200, resp.text
    meta = resp.json()["metadata"]
    assert meta["doi"] == "10.2/y"
    # Empty / None resolved values are skipped, not written as blanks.
    assert "publisher" not in meta
    assert "language" not in meta


def test_resolve_isbn_fallback_when_doi_empty(client, db, monkeypatch):
    doc = Document(name="book.pdf", source_metadata={})
    db.save(doc)
    _stub_resolvers(
        monkeypatch,
        doi_result={},  # DOI yields nothing -> fall through to ISBN
        isbn_result={"title": "From ISBN", "isbn_13": "9783161484100"},
    )

    resp = client.post(
        f"/api/bibliography/resolve?document_id={doc.id}",
        json={"doi": "10.3/z", "isbn": "9783161484100"},
    )
    assert resp.status_code == 200, resp.text
    meta = resp.json()["metadata"]
    assert meta["title"] == "From ISBN"
    assert meta["isbn_13"] == "9783161484100"


def test_resolve_unknown_document_id_404(client, db, monkeypatch):
    _stub_resolvers(monkeypatch, doi_result={"title": "Resolved"})
    resp = client.post(
        "/api/bibliography/resolve?document_id=does-not-exist",
        json={"doi": "10.1/x"},
    )
    assert resp.status_code == 404


def test_resolve_nothing_resolves_404(client, db, monkeypatch):
    _stub_resolvers(monkeypatch, doi_result={}, isbn_result={})
    resp = client.post(
        "/api/bibliography/resolve",
        json={"doi": "10.1/x", "isbn": "9783161484100"},
    )
    assert resp.status_code == 404


def test_resolve_without_document_id_returns_resolved_unattached(client, db, monkeypatch):
    _stub_resolvers(monkeypatch, doi_result={"title": "Loose", "doi": "10.4/q"})
    resp = client.post("/api/bibliography/resolve", json={"doi": "10.4/q"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # Not associated with any document.
    assert body["document_id"] == ""
    assert body["metadata"] == {"title": "Loose", "doi": "10.4/q"}


# ---------------------------------------------------------------------------
# export_bibtex() — multi-doc, skip empties, skip unknowns
# ---------------------------------------------------------------------------


def test_export_bibtex_concatenates_multiple_docs(client, db):
    a = Document(name="a", source_metadata={"title": "First", "date": "1999"})
    b = Document(name="b", source_metadata={"title": "Second", "date": "2001"})
    db.save(a)
    db.save(b)

    resp = client.post(
        "/api/bibliography/export.bib",
        json={"document_ids": [a.id, b.id]},
    )
    assert resp.status_code == 200, resp.text
    titles = {e["title"] for e in read_bibtex(resp.text)}
    assert titles == {"First", "Second"}


def test_export_bibtex_skips_docs_without_metadata(client, db):
    good = Document(name="good", source_metadata={"title": "Kept", "date": "2000"})
    empty = Document(name="empty", source_metadata={})
    none_meta = Document(name="none", source_metadata=None)
    db.save(good)
    db.save(empty)
    db.save(none_meta)

    resp = client.post(
        "/api/bibliography/export.bib",
        json={"document_ids": [good.id, empty.id, none_meta.id]},
    )
    assert resp.status_code == 200, resp.text
    titles = [e["title"] for e in read_bibtex(resp.text)]
    assert titles == ["Kept"]  # empty / None metadata docs skipped, not errored


def test_export_bibtex_skips_unknown_ids(client, db):
    good = Document(name="good", source_metadata={"title": "Only", "date": "2000"})
    db.save(good)

    resp = client.post(
        "/api/bibliography/export.bib",
        json={"document_ids": ["missing-1", good.id, "missing-2"]},
    )
    assert resp.status_code == 200, resp.text
    assert [e["title"] for e in read_bibtex(resp.text)] == ["Only"]


def test_export_bibtex_empty_request_is_empty(client, db):
    resp = client.post("/api/bibliography/export.bib", json={"document_ids": []})
    assert resp.status_code == 200, resp.text
    assert resp.text.strip() == ""
