"""Direct tests for citation_rendering._metadata_for_document (#1979 Test Coverage).

The citation_rendering route module was unreached by tests. Its source-metadata
resolver has the branchy logic worth covering: prefer the document's own
``metadata['source_metadata']``, fall through silently if that dict fails to
parse, then fall back to the most-recent claim, else None.
"""

from __future__ import annotations

from fichero.api.routes.citation_rendering import _metadata_for_document
from fichero.knowledge_models import KnowledgeClaim, SourceMetadata
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
