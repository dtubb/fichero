"""Direct tests for citation_rendering._metadata_for_document (#1979 Test Coverage).

The citation_rendering route module was unreached by tests. Its source-metadata
resolver has the branchy logic worth covering: prefer the document's own
``metadata['source_metadata']``, fall through silently if that dict fails to
parse, then fall back to the most-recent claim, else None.
"""

from __future__ import annotations

from fichero.api.routes.citation.rendering import _metadata_for_document
from fichero.models.knowledge import KnowledgeClaim, SourceMetadata
from fichero.models import Document


class _StubDB:
    def __init__(self, doc: Document | None = None, claims=()):
        self._doc = doc
        self._claims = list(claims)

    def get(self, _model, _id):
        return self._doc

    def query(self, _model, source_document_id=None):
        return list(self._claims)


def _doc_with_source_metadata(value) -> Document:
    return Document(id="d1", name="d1", metadata={"source_metadata": value})


def test_returns_document_source_metadata_when_present_and_valid() -> None:
    db = _StubDB(doc=_doc_with_source_metadata({"title": "On Archives"}))
    meta = _metadata_for_document(db, "d1")
    assert isinstance(meta, SourceMetadata)
    assert meta.title == "On Archives"


def test_invalid_document_source_metadata_falls_through_to_claim() -> None:
    # authors must be a list; an int fails validation -> the except: pass branch
    # is taken and we fall back to the claim instead of crashing.
    claim_meta = SourceMetadata(title="From Claim")
    claim = KnowledgeClaim(text="c", source_metadata=claim_meta)
    db = _StubDB(doc=_doc_with_source_metadata({"authors": 123}), claims=[claim])
    meta = _metadata_for_document(db, "d1")
    assert meta is claim_meta


def test_document_without_source_metadata_falls_back_to_claim() -> None:
    claim_meta = SourceMetadata(title="Claim Only")
    claim = KnowledgeClaim(text="c", source_metadata=claim_meta)
    db = _StubDB(doc=Document(id="d1", name="d1"), claims=[claim])
    assert _metadata_for_document(db, "d1") is claim_meta


def test_missing_document_still_uses_claim_fallback() -> None:
    claim_meta = SourceMetadata(title="No Doc")
    claim = KnowledgeClaim(text="c", source_metadata=claim_meta)
    db = _StubDB(doc=None, claims=[claim])
    assert _metadata_for_document(db, "d1") is claim_meta


def test_first_claim_with_source_metadata_wins() -> None:
    wanted = SourceMetadata(title="Second")
    claims = [
        KnowledgeClaim(text="c1", source_metadata=None),
        KnowledgeClaim(text="c2", source_metadata=wanted),
    ]
    db = _StubDB(doc=Document(id="d1", name="d1"), claims=claims)
    assert _metadata_for_document(db, "d1") is wanted


def test_returns_none_when_no_metadata_anywhere() -> None:
    db = _StubDB(doc=Document(id="d1", name="d1"), claims=[])
    assert _metadata_for_document(db, "d1") is None


# ---------------------------------------------------------------------------
# #3251 regression: source_metadata on Document.source_metadata (top-level)
# ---------------------------------------------------------------------------


def test_prefers_document_source_metadata_field_over_metadata_dict() -> None:
    """When both doc.source_metadata and doc.metadata['source_metadata'] exist,
    the top-level field wins (it's the authoritative writer location)."""
    from fichero.models.knowledge import SourceMetadata

    doc = Document(
        id="d1",
        name="d1",
        source_metadata={"title": "Top-Level"},
        metadata={"source_metadata": {"title": "Nested Dict"}},
    )
    db = _StubDB(doc=doc)
    meta = _metadata_for_document(db, "d1")
    assert isinstance(meta, SourceMetadata)
    assert meta.title == "Top-Level"


def test_reads_document_source_metadata_when_dict_stored() -> None:
    """doc.source_metadata may be stored as a plain dict in DuckDB;
    _metadata_for_document should construct SourceMetadata from it."""
    doc = Document(
        id="d1",
        name="d1",
        source_metadata={"title": "Dict As Field", "authors": ["Author A"]},
    )
    db = _StubDB(doc=doc)
    meta = _metadata_for_document(db, "d1")
    assert isinstance(meta, SourceMetadata)
    assert meta.title == "Dict As Field"


def test_source_metadata_field_with_invalid_dict_falls_through() -> None:
    """If doc.source_metadata is a dict that can't construct a valid
    SourceMetadata, fall through to legacy dict or claims."""
    claim_meta = SourceMetadata(title="From Claim")
    claim = KnowledgeClaim(text="c", source_metadata=claim_meta)
    doc = Document(
        id="d1",
        name="d1",
        source_metadata={"authors": 123},  # invalid: authors should be list
    )
    db = _StubDB(doc=doc, claims=[claim])
    meta = _metadata_for_document(db, "d1")
    assert meta is claim_meta


def test_legacy_metadata_dict_still_works_when_no_top_level_field() -> None:
    """Older libraries that only wrote to doc.metadata['source_metadata']
    should still be read correctly."""
    doc = Document(
        id="d1",
        name="d1",
        source_metadata=None,
        metadata={"source_metadata": {"title": "Legacy Path"}},
    )
    db = _StubDB(doc=doc)
    meta = _metadata_for_document(db, "d1")
    assert isinstance(meta, SourceMetadata)
    assert meta.title == "Legacy Path"
